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

MAX_BATCH_SIZE = 500


def clean_and_validate_flag(
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


class FlagSubmission(BaseModel):
    flag: str = Field(
        min_length=1,
        max_length=512,
    )

    service: str | None = None
    source: str | None = None

    @field_validator("flag")
    @classmethod
    def validate_flag(
        cls,
        value: str,
    ) -> str:
        return clean_and_validate_flag(value)


class BatchFlagSubmission(BaseModel):
    flags: list[str] = Field(
        min_length=1,
        max_length=MAX_BATCH_SIZE,
    )

    service: str | None = None
    source: str | None = None


async def _process_valid_flag(
    flag: str,
    *,
    service: str | None,
    source: str | None,
) -> dict[str, object]:
    if has_flag(flag):
        return {
            "status": "duplicate",
            "code": "LOCAL",
            "message": (
                "mof has already seen this offering"
            ),
            "remembered": True,
        }

    outcome = await submit_once(
        flag,
        submitter=submit_to_gameserver,
    )

    if outcome.terminal:
        state = TERMINAL_STATE
    else:
        state = RETRYABLE_STATE

    record_submission(
        flag,
        state=state,
        response_code=outcome.code,
        response_message=outcome.message,
        service=service,
        source=source,
    )

    return {
        "status": "submitted",
        "code": outcome.code,
        "message": outcome.message,
        "remembered": outcome.terminal,
    }


@router.post("/flags")
async def submit_flag(
    submission: FlagSubmission,
):
    result = await _process_valid_flag(
        submission.flag,
        service=submission.service,
        source=submission.source,
    )

    if result["code"] == "TIMEOUT":
        raise HTTPException(
            status_code=504,
            detail=result["message"],
        )

    if result["code"] == "CONNECTION_ERROR":
        raise HTTPException(
            status_code=502,
            detail=result["message"],
        )

    return result


@router.post("/flags/batch")
async def submit_flag_batch(
    submission: BatchFlagSubmission,
):
    summary = {
        "received": len(submission.flags),
        "accepted": 0,
        "duplicate": 0,
        "terminal_other": 0,
        "retryable": 0,
        "invalid": 0,
    }

    results = []

    seen: set[str] = set()
    first_results: dict[
        str,
        dict[str, object],
    ] = {}

    for index, raw_flag in enumerate(
        submission.flags
    ):
        try:
            flag = clean_and_validate_flag(
                raw_flag
            )

        except ValueError as exc:
            result = {
                "index": index,
                "status": "invalid",
                "code": "INVALID_FORMAT",
                "message": str(exc),
                "remembered": False,
            }

            summary["invalid"] += 1
            results.append(result)

            continue

        if flag in seen:
            first_result = first_results[
                flag
            ]

            result = {
                "index": index,
                "status": "duplicate",
                "code": "BATCH",
                "message": (
                    "mof found this offering "
                    "twice in the same bundle"
                ),
                "remembered": (
                    first_result["remembered"]
                ),
            }

            summary["duplicate"] += 1
            results.append(result)

            continue

        seen.add(flag)

        processed = await _process_valid_flag(
            flag,
            service=submission.service,
            source=submission.source,
        )

        first_results[flag] = processed

        result = {
            "index": index,
            **processed,
        }

        results.append(result)

        code = processed["code"]

        if processed["status"] == "duplicate":
            summary["duplicate"] += 1

        elif code == "DUP":
            summary["duplicate"] += 1

        elif code == "OK":
            summary["accepted"] += 1

        elif processed["remembered"] is False:
            summary["retryable"] += 1

        else:
            summary["terminal_other"] += 1

    return {
        "status": "processed",
        "summary": summary,
        "results": results,
    }