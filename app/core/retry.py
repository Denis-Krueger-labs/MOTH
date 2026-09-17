from dataclasses import dataclass
from uuid import uuid4

from app.core.submission_service import submit_once
from app.core.submitter import (
    submit_flag as submit_to_gameserver,
)
from app.db.database import (
    DEFAULT_RETRY_LEASE_SECONDS,
    RETRYABLE_STATE,
    TERMINAL_STATE,
    claim_due_retryable_submission,
    record_claimed_submission,
)
from app.db.events import (
    record_event_safely,
)


@dataclass
class RetryAttempt:
    record_id: int
    state: str
    code: str
    message: str | None
    recorded: bool


def _new_worker_id() -> str:
    return f"retry-{uuid4().hex}"


async def retry_pending_once(
    limit: int = 100,
    worker_id: str | None = None,
    lease_seconds: int = DEFAULT_RETRY_LEASE_SECONDS,
) -> list[RetryAttempt]:
    if limit <= 0:
        raise ValueError(
            "mof needs a positive retry worker limit"
        )

    if worker_id is None:
        worker_id = _new_worker_id()

    worker_id = worker_id.strip()

    if not worker_id:
        raise ValueError(
            "MORI refuses to run an unnamed retry worker"
        )

    if lease_seconds <= 0:
        raise ValueError(
            "MORI requires a positive retry lease duration"
        )

    attempts = []

    for _ in range(limit):
        candidate = (
            claim_due_retryable_submission(
                worker_id,
                lease_seconds=lease_seconds,
            )
        )

        if candidate is None:
            break

        if candidate.lease_token is None:
            raise RuntimeError(
                "MORI issued a retry claim "
                "without a fencing token"
            )

        outcome = await submit_once(
            candidate.flag,
            submitter=submit_to_gameserver,
        )

        if outcome.terminal:
            state = TERMINAL_STATE
        else:
            state = RETRYABLE_STATE

        recorded = record_claimed_submission(
            candidate.flag,
            worker_id,
            candidate.lease_token,
            state=state,
            response_code=outcome.code,
            response_message=outcome.message,
            service=candidate.service,
            source=candidate.source,
        )

        if recorded:
            record_event_safely(
                "retry",
                code=outcome.code,
                state=state,
                service=candidate.service,
                source=candidate.source,
                worker_id=worker_id,
            )

        else:
            record_event_safely(
                "retry_stale",
                code=outcome.code,
                state="rejected",
                service=candidate.service,
                source=candidate.source,
                worker_id=worker_id,
            )

        attempts.append(
            RetryAttempt(
                record_id=candidate.id,
                state=state,
                code=outcome.code,
                message=outcome.message,
                recorded=recorded,
            )
        )

        if not recorded:
            break

    return attempts