"""Configure the FastAPI application and its startup and shutdown lifecycle."""

import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.dashboard import (
    router as dashboard_router,
)
from app.api.flags import (
    router as flags_router,
)
from app.api.health import (
    router as health_router,
)
from app.core import scheduler
from app.db import database
from app.db import events
from app.db import submission_gate


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialize persistence and scheduling, then flush pending events on shutdown."""
    database.initialize_database()
    events.initialize_event_history()

    submission_gate.initialize_submission_gate()

    stop_event = asyncio.Event()

    scheduler_task = asyncio.create_task(
        scheduler.run_retry_scheduler(
            stop_event
        ),
        name="moth-retry-scheduler",
    )

    app.state.retry_scheduler_stop_event = (
        stop_event
    )

    app.state.retry_scheduler_task = (
        scheduler_task
    )

    try:
        yield

    finally:
        stop_event.set()

        await scheduler_task

        events.flush_batched_events()


app = FastAPI(
    title="MOTH",
    description=(
        "Multi-Operator Transmission Hub"
    ),
    lifespan=lifespan,
)


app.include_router(
    health_router
)

app.include_router(
    flags_router
)

app.include_router(
    dashboard_router
)


@app.get("/")
async def root():
    return {
        "name": "MOTH",
        "status": "alive",
        "message": (
            "mof is watching the lämp"
        ),
    }
