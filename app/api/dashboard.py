"""Provide authenticated dashboard statistics, activity, and health endpoints."""

from dataclasses import asdict

from fastapi import (
    APIRouter,
    Depends,
    Query,
    Request,
)
from starlette.concurrency import (
    run_in_threadpool,
)

from app.core.auth import require_api_token
from app.core.operational_health import (
    build_operational_health,
    probe_submission_server,
)
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
def dashboard_stats():
    return get_dashboard_stats()


@router.get("/recent")
def dashboard_recent(
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


@router.get("/health")
async def dashboard_health(
    request: Request,
):
    stats = await run_in_threadpool(
        get_dashboard_stats
    )

    return build_operational_health(
        request.app,
        stats,
    )


@router.get("/connectivity")
async def dashboard_connectivity():
    return await probe_submission_server()
