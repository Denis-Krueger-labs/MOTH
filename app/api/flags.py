from fastapi import APIRouter
from pydantic import BaseModel, Field, field_validator

from app.db.database import store_flag


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
    stored = store_flag(submission.flag)

    if not stored:
        return {
            "status": "duplicate",
            "message": "mof has already seen this offering",
        }

    return {
        "status": "stored",
        "message": "mof carried the flag into the nest",
    }