from dataclasses import dataclass

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
    RETRYABLE_STATE,
    TERMINAL_STATE,
    get_retryable_submissions,
    record_submission,
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


async def retry_pending_once(
    limit: int = 100,
) -> list[RetryAttempt]:
    candidates = get_retryable_submissions(
        limit=limit,
    )

    attempts = []

    for candidate in candidates:
        try:
            result = await submit_to_gameserver(
                candidate.flag,
                host=get_submission_host(),
                port=get_submission_port(),
                timeout=get_submission_timeout(),
            )

        except SubmissionTimeoutError as exc:
            record_submission(
                candidate.flag,
                state=RETRYABLE_STATE,
                response_code="TIMEOUT",
                response_message=str(exc),
                service=candidate.service,
                source=candidate.source,
            )

            attempts.append(
                RetryAttempt(
                    record_id=candidate.id,
                    state=RETRYABLE_STATE,
                    code="TIMEOUT",
                    message=str(exc),
                )
            )

            continue

        except SubmissionConnectionError as exc:
            record_submission(
                candidate.flag,
                state=RETRYABLE_STATE,
                response_code="CONNECTION_ERROR",
                response_message=str(exc),
                service=candidate.service,
                source=candidate.source,
            )

            attempts.append(
                RetryAttempt(
                    record_id=candidate.id,
                    state=RETRYABLE_STATE,
                    code="CONNECTION_ERROR",
                    message=str(exc),
                )
            )

            continue

        except ValueError as exc:
            record_submission(
                candidate.flag,
                state=RETRYABLE_STATE,
                response_code="PROTOCOL_ERROR",
                response_message=str(exc),
                service=candidate.service,
                source=candidate.source,
            )

            attempts.append(
                RetryAttempt(
                    record_id=candidate.id,
                    state=RETRYABLE_STATE,
                    code="PROTOCOL_ERROR",
                    message=str(exc),
                )
            )

            continue

        if result.code in TERMINAL_SUBMISSION_CODES:
            state = TERMINAL_STATE
        else:
            state = RETRYABLE_STATE

        record_submission(
            candidate.flag,
            state=state,
            response_code=result.code,
            response_message=result.message,
            service=candidate.service,
            source=candidate.source,
        )

        attempts.append(
            RetryAttempt(
                record_id=candidate.id,
                state=state,
                code=result.code,
                message=result.message,
            )
        )

    return attempts