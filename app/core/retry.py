from dataclasses import dataclass
from uuid import uuid4

from app.core.config import (
    get_submission_host,
    get_submission_port,
    get_submission_timeout,
)
from app.core.submitter import (
    SubmissionConnectionError,
    SubmissionTimeoutError,
    submit_flag as submit_to_gameserver,
)
from app.db.database import (
    DEFAULT_RETRY_LEASE_SECONDS,
    RETRYABLE_STATE,
    TERMINAL_STATE,
    claim_due_retryable_submission,
    record_claimed_submission,
)


TERMINAL_SUBMISSION_CODES = {
    "OK",
    "DUP",
    "OWN",
    "OLD",
    "INV",
}


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
        candidate = claim_due_retryable_submission(
            worker_id,
            lease_seconds=lease_seconds,
        )

        if candidate is None:
            break

        if candidate.lease_token is None:
            raise RuntimeError(
                "MORI issued a retry claim without a fencing token"
            )

        try:
            result = await submit_to_gameserver(
                candidate.flag,
                host=get_submission_host(),
                port=get_submission_port(),
                timeout=get_submission_timeout(),
            )

        except SubmissionTimeoutError as exc:
            state = RETRYABLE_STATE
            code = "TIMEOUT"
            message = str(exc)

        except SubmissionConnectionError as exc:
            state = RETRYABLE_STATE
            code = "CONNECTION_ERROR"
            message = str(exc)

        except ValueError as exc:
            state = RETRYABLE_STATE
            code = "PROTOCOL_ERROR"
            message = str(exc)

        else:
            code = result.code
            message = result.message

            if code in TERMINAL_SUBMISSION_CODES:
                state = TERMINAL_STATE
            else:
                state = RETRYABLE_STATE

        recorded = record_claimed_submission(
            candidate.flag,
            worker_id,
            candidate.lease_token,
            state=state,
            response_code=code,
            response_message=message,
            service=candidate.service,
            source=candidate.source,
        )

        attempts.append(
            RetryAttempt(
                record_id=candidate.id,
                state=state,
                code=code,
                message=message,
                recorded=recorded,
            )
        )

        if not recorded:
            break

    return attempts