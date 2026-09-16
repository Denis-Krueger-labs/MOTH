from fastapi import APIRouter

router = APIRouter(
    prefix="/api",
    tags=["health"],
)


@router.get("/health")
async def health():
    return {
        "status": "alive",
        "mori": "watching",
        "moth": "awake",
    }