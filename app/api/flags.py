import asyncio
import re

from uuid import uuid4

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

from app.core.submission_capacity import (
    SubmissionCapacity,
)

from app.core.submission_service import (
    submit_once,
)

from app.core.submitter import (
    submit_flag as submit_to_gameserver,
)

from app.db.database import (
    RETRYABLE_STATE,
    TERMINAL_STATE,
)

from app.db.events import (
    record_batched_event_safely,
    record_event_safely,
)

from app.db.submission_gate import (
    claim_initial_submission,
    finalize_initial_submission,
    release_initial_submission,
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
MAX_BATCH_CONCURRENCY = 8


submission_capacity = SubmissionCapacity()


def clean_and_validate_flag(
    value: str,
) -> str:
    value = value.strip()

    if not value:
        raise ValueError(
            "mof refuses to carry an empty flag"
        )

    if (
        FAUST_FLAG_PATTERN.fullmatch(
            value
        )
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
        return clean_and_validate_flag(
            value
        )


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
    worker_id = (
        f"initial-{uuid4().hex}"
    )

    claim = claim_initial_submission(
        flag,
        worker_id,
    )

    if claim.status == "existing":
        if (
            claim.existing_state
            == RETRYABLE_STATE
        ):
            record_event_safely(
                "duplicate",
                code="LOCAL_RETRY",
                state="retryable",
                service=service,
                source=source,
            )

            return {
                "status": "queued",
                "code": "LOCAL_RETRY",
                "message": (
                    "mof already has this "
                    "offering queued for retry"
                ),
                "remembered": False,
            }

        record_event_safely(
            "duplicate",
            code="LOCAL",
            state="terminal",
            service=service,
            source=source,
        )

        return {
            "status": "duplicate",
            "code": "LOCAL",
            "message": (
                "mof has already seen "
                "this offering"
            ),
            "remembered": True,
        }

    if claim.status == "busy":
        record_event_safely(
            "duplicate",
            code="IN_FLIGHT",
            state="in_flight",
            service=service,
            source=source,
        )

        return {
            "status": "in_flight",
            "code": "IN_FLIGHT",
            "message": (
                "MORI is already guarding "
                "this offering while mof "
                "submits it"
            ),
            "remembered": False,
        }

    if (
        claim.status != "claimed"
        or claim.lease_token is None
    ):
        raise RuntimeError(
            "MORI produced an invalid "
            "initial submission claim"
        )

    acquired = (
        submission_capacity.try_acquire()
    )

    if not acquired:
        release_initial_submission(
            flag,
            worker_id,
            claim.lease_token,
        )

        record_batched_event_safely(
            "submission_overload",
            code="OVERLOADED",
            state="rejected",
            service=service,
            source=source,
        )

        return {
            "status": "overloaded",
            "code": "OVERLOADED",
            "message": (
                "MORI refuses another submission "
                "until the nest has capacity"
            ),
            "remembered": False,
        }

    finalized = False

    try:
        outcome = await submit_once(
            flag,
            submitter=submit_to_gameserver,
        )

        if outcome.terminal:
            state = TERMINAL_STATE
        else:
            state = RETRYABLE_STATE

        finalized = (
            finalize_initial_submission(
                flag,
                worker_id,
                claim.lease_token,
                state=state,
                response_code=outcome.code,
                response_message=outcome.message,
                service=service,
                source=source,
            )
        )

        if not finalized:
            record_batched_event_safely(
                "initial_stale",
                code="STALE_CLAIM",
                state="rejected",
                service=service,
                source=source,
            )

            return {
                "status": "retryable",
                "code": "STALE_CLAIM",
                "message": (
                    "MORI rejected a stale "
                    "initial submission result; "
                    "retry the offering"
                ),
                "remembered": False,
            }

        return {
            "status": "submitted",
            "code": outcome.code,
            "message": outcome.message,
            "remembered": (
                outcome.terminal
            ),
        }

    finally:
        submission_capacity.release()

        if not finalized:
            release_initial_submission(
                flag,
                worker_id,
                claim.lease_token,
            )


def _update_batch_summary(
    summary: dict[str, int],
    processed: dict[str, object],
) -> None:
    code = processed["code"]

    if (
        processed["status"]
        == "duplicate"
    ):
        summary[
            "duplicate"
        ] += 1

    elif (
        processed["status"]
        == "in_flight"
    ):
        summary[
            "in_flight"
        ] += 1

    elif (
        processed["status"]
        == "overloaded"
    ):
        summary[
            "overloaded"
        ] += 1

    elif code == "DUP":
        summary[
            "duplicate"
        ] += 1

    elif code == "OK":
        summary[
            "accepted"
        ] += 1

    elif (
        processed["remembered"]
        is False
    ):
        summary[
            "retryable"
        ] += 1

    else:
        summary[
            "terminal_other"
        ] += 1


@router.post("/flags")
async def submit_flag(
    submission: FlagSubmission,
):
    result = await _process_valid_flag(
        submission.flag,
        service=submission.service,
        source=submission.source,
    )

    if result["code"] in {
        "OVERLOADED",
        "STALE_CLAIM",
    }:
        raise HTTPException(
            status_code=503,
            detail=result["message"],
            headers={
                "Retry-After": "1",
            },
        )

    if result["code"] == "TIMEOUT":
        raise HTTPException(
            status_code=504,
            detail=result["message"],
        )

    if (
        result["code"]
        == "CONNECTION_ERROR"
    ):
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
        "received": len(
            submission.flags
        ),
        "accepted": 0,
        "duplicate": 0,
        "terminal_other": 0,
        "retryable": 0,
        "invalid": 0,
        "in_flight": 0,
        "overloaded": 0,
    }

    results_by_index: dict[
        int,
        dict[str, object],
    ] = {}

    first_index_by_flag: dict[
        str,
        int,
    ] = {}

    unique_flags: list[
        tuple[int, str]
    ] = []

    duplicate_flags: list[
        tuple[int, str]
    ] = []

    for index, raw_flag in enumerate(
        submission.flags
    ):
        try:
            flag = (
                clean_and_validate_flag(
                    raw_flag
                )
            )

        except ValueError as exc:
            record_event_safely(
                "invalid",
                code="INVALID_FORMAT",
                state="rejected",
                service=submission.service,
                source=submission.source,
            )

            results_by_index[index] = {
                "index": index,
                "status": "invalid",
                "code": "INVALID_FORMAT",
                "message": str(exc),
                "remembered": False,
            }

            summary[
                "invalid"
            ] += 1

            continue

        if flag in first_index_by_flag:
            duplicate_flags.append(
                (
                    index,
                    flag,
                )
            )

            continue

        first_index_by_flag[
            flag
        ] = index

        unique_flags.append(
            (
                index,
                flag,
            )
        )

    semaphore = asyncio.Semaphore(
        MAX_BATCH_CONCURRENCY
    )

    async def process_unique(
        index: int,
        flag: str,
    ) -> tuple[
        int,
        str,
        dict[str, object],
    ]:
        async with semaphore:
            processed = (
                await _process_valid_flag(
                    flag,
                    service=(
                        submission.service
                    ),
                    source=(
                        submission.source
                    ),
                )
            )

        return (
            index,
            flag,
            processed,
        )

    processed_unique = await asyncio.gather(
        *(
            process_unique(
                index,
                flag,
            )
            for index, flag in unique_flags
        )
    )

    first_results: dict[
        str,
        dict[str, object],
    ] = {}

    for (
        index,
        flag,
        processed,
    ) in processed_unique:
        first_results[
            flag
        ] = processed

        results_by_index[index] = {
            "index": index,
            **processed,
        }

        _update_batch_summary(
            summary,
            processed,
        )

    for index, flag in duplicate_flags:
        first_result = (
            first_results[
                flag
            ]
        )

        record_event_safely(
            "duplicate",
            code="BATCH",
            state="local",
            service=submission.service,
            source=submission.source,
        )

        results_by_index[index] = {
            "index": index,
            "status": "duplicate",
            "code": "BATCH",
            "message": (
                "mof found this offering "
                "twice in the same bundle"
            ),
            "remembered": (
                first_result[
                    "remembered"
                ]
            ),
        }

        summary[
            "duplicate"
        ] += 1

    results = [
        results_by_index[index]
        for index in range(
            len(submission.flags)
        )
    ]

    return {
        "status": "processed",
        "summary": summary,
        "results": results,
    }