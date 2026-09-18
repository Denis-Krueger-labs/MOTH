"""Translate one game-server submission attempt into a durable outcome."""

from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from app.core.config import (
    get_submission_host,
    get_submission_port,
    get_submission_timeout,
)
from app.core.submitter import (
    SubmissionConnectionError,
    SubmissionResult,
    SubmissionTimeoutError,
    submit_flag as default_submitter,
)


TERMINAL_SUBMISSION_CODES = frozenset(
    {
        "OK",
        "DUP",
        "OWN",
        "OLD",
        "INV",
    }
)


Submitter = Callable[
    [str, str, int, float],
    Awaitable[SubmissionResult],
]


@dataclass(frozen=True, slots=True)
class SubmissionOutcome:
    """Describe one normalized submission result and its retry eligibility."""

    code: str
    message: str | None
    terminal: bool


async def submit_once(
    flag: str,
    *,
    submitter: Submitter = default_submitter,
) -> SubmissionOutcome:
    """Convert a game-server attempt into a terminal or retryable outcome."""
    try:
        result = await submitter(
            flag,
            host=get_submission_host(),
            port=get_submission_port(),
            timeout=get_submission_timeout(),
        )

    except SubmissionTimeoutError as exc:
        return SubmissionOutcome(
            code="TIMEOUT",
            message=str(exc),
            terminal=False,
        )

    except SubmissionConnectionError as exc:
        return SubmissionOutcome(
            code="CONNECTION_ERROR",
            message=str(exc),
            terminal=False,
        )

    except ValueError as exc:
        return SubmissionOutcome(
            code="PROTOCOL_ERROR",
            message=str(exc),
            terminal=False,
        )

    return SubmissionOutcome(
        code=result.code,
        message=result.message,
        terminal=(
            result.code
            in TERMINAL_SUBMISSION_CODES
        ),
    )
