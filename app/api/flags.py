from fastapi import APIRouter
from pydantic import BaseModel, Field, field_validator


router = APIRouter(
    prefix="/api",
    tags=["flags"],
)


class FlagSubmission(BaseModel):
    flag: str = Field(min_length=1, max_length=512)
    service: str | None = None
    source: str | None = None

    @field_validator("flag")
    @classmethod
    def clean_flag(cls, value: str) -> str:
        value = value.strip()

        if not value:
            raise ValueError("mof refuses to carry an empty flag")

        return value


@router.post("/flags")
async def submit_flag(submission: FlagSubmission):
    return {
        "status": "received",
        "flag": submission.flag,
        "service": submission.service,
        "source": submission.source,
        "message": "mof acquired a suspicious string",
    }