from fastapi import APIRouter
from pydantic import BaseModel


router = APIRouter(
    prefix="/api",
    tags=["flags"],
)


class FlagSubmission(BaseModel):
    flag: str
    service: str | None = None
    source: str | None = None


@router.post("/flags")
async def submit_flag(submission: FlagSubmission):
    return {
        "status": "received",
        "flag": submission.flag,
        "service": submission.service,
        "source": submission.source,
        "message": "mof acquired a suspicious string",
    }