from dataclasses import asdict

from fastapi import (
    APIRouter,
    Depends,
    Query,
)

from app.core.auth import require_api_token
from app.db.dashboard import (
    get_dashboard_stats,
)
from app.db.events import (
    get_recent_events,
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


@router.get("/recent")
async def dashboard_recent(
    limit: int = Query(
        default=50,
        ge=1,
        le=500,
    ),
):
    events = get_recent_events(
        limit=limit
    )

    return {
        "count": len(events),
        "events": [
            asdict(event)
            for event in events
        ],
    }