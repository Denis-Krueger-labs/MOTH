from fastapi import (
    APIRouter,
    Depends,
)

from app.core.auth import require_api_token
from app.db.dashboard import (
    get_dashboard_stats,
)


router = APIRouter(
    prefix="/api/dashboard",
    tags=["dashboard"],
    dependencies=[
        Depends(require_api_token)
    ],
)


@router.get("/stats")
async def dashboard_stats():
    return get_dashboard_stats()