import re

from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
)
from pydantic import (
    BaseModel,
    Field,
    field_validator,
)

from app.core.auth import require_api_token
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
    has_flag,
    record_submission,
)


router = APIRouter(
    prefix="/api",
    tags=["flags"],
    dependencies=[
        Depends(require_api_token),
    ],
)


FAUST_FLAG_PATTERN = re.compile(
    r"FAUST_[A-Za-z0-9/+]{32}"
)


TERMINAL_SUBMISSION_CODES = {
    "OK",
    "DUP",
    "OWN",
    "OLD",
    "INV",
}


class FlagSubmission(BaseModel):
    flag: str = Field(
        min_length=1,
        max_length=512,
    )
    service: str | None = None
    source: str | None = None

    @field_validator("flag")
    @classmethod
    def clean_and_validate_flag(
        cls,
        value: str,
    ) -> str:
        value = value.strip()

        if not value:
            raise ValueError(
                "mof refuses to carry an empty flag"
            )

        if FAUST_FLAG_PATTERN.fullmatch(value) is None:
            raise ValueError(
                "mof does not recognize this as a FAUST flag"
            )

        return value


@router.post("/flags")
async def submit_flag(
    submission: FlagSubmission,
):
    if has_flag(submission.flag):
        return {
            "status": "duplicate",
            "code": "LOCAL",
            "message": (
                "mof has already seen this offering"
            ),
            "remembered": True,
        }

    try:
        result = await submit_to_gameserver(
            submission.flag,
            host=get_submission_host(),
            port=get_submission_port(),
            timeout=get_submission_timeout(),
        )

    except SubmissionTimeoutError as exc:
        record_submission(
            submission.flag,
            state=RETRYABLE_STATE,
            response_code="TIMEOUT",
            response_message=str(exc),
            service=submission.service,
            source=submission.source,
        )

        raise HTTPException(
            status_code=504,
            detail=str(exc),
        ) from exc

    except SubmissionConnectionError as exc:
        record_submission(
            submission.flag,
            state=RETRYABLE_STATE,
            response_code="CONNECTION_ERROR",
            response_message=str(exc),
            service=submission.service,
            source=submission.source,
        )

        raise HTTPException(
            status_code=502,
            detail=str(exc),
        ) from exc

    if result.code in TERMINAL_SUBMISSION_CODES:
        state = TERMINAL_STATE
    else:
        state = RETRYABLE_STATE

    record_submission(
        submission.flag,
        state=state,
        response_code=result.code,
        response_message=result.message,
        service=submission.service,
        source=submission.source,
    )

    return {
        "status": "submitted",
        "code": result.code,
        "message": result.message,
        "remembered": state == TERMINAL_STATE,
    }