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
from app.core.submission_service import submit_once
from app.core.submitter import (
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
        Depends(require_api_token)
    ],
)


FAUST_FLAG_PATTERN = re.compile(
    r"FAUST_[A-Za-z0-9/+]{32}"
)


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

        if (
            FAUST_FLAG_PATTERN.fullmatch(value)
            is None
        ):
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

    outcome = await submit_once(
        submission.flag,
        submitter=submit_to_gameserver,
    )

    if outcome.terminal:
        state = TERMINAL_STATE
    else:
        state = RETRYABLE_STATE

    record_submission(
        submission.flag,
        state=state,
        response_code=outcome.code,
        response_message=outcome.message,
        service=submission.service,
        source=submission.source,
    )

    if outcome.code == "TIMEOUT":
        raise HTTPException(
            status_code=504,
            detail=outcome.message,
        )

    if outcome.code == "CONNECTION_ERROR":
        raise HTTPException(
            status_code=502,
            detail=outcome.message,
        )

    return {
        "status": "submitted",
        "code": outcome.code,
        "message": outcome.message,
        "remembered": outcome.terminal,
    }