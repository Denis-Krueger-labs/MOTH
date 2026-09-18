"""Run the background scheduler that periodically processes retryable flags."""

import asyncio
import logging
from uuid import uuid4

from app.core.retry import retry_pending_once


logger = logging.getLogger(__name__)


DEFAULT_RETRY_INTERVAL_SECONDS = 1.0
DEFAULT_RETRY_BATCH_LIMIT = 100


def _new_scheduler_worker_id() -> str:
    """Create an identity reused across a single scheduler lifetime."""
    return f"scheduler-{uuid4().hex}"


async def run_retry_scheduler(
    stop_event: asyncio.Event,
    *,
    interval_seconds: float = DEFAULT_RETRY_INTERVAL_SECONDS,
    retry_limit: int = DEFAULT_RETRY_BATCH_LIMIT,
    worker_id: str | None = None,
) -> None:
    """Process retry batches until stopped while surviving recoverable failures."""
    if interval_seconds <= 0:
        raise ValueError(
            "mof needs a positive scheduler interval"
        )

    if retry_limit <= 0:
        raise ValueError(
            "mof needs a positive scheduler retry limit"
        )

    if worker_id is None:
        worker_id = _new_scheduler_worker_id()

    worker_id = worker_id.strip()

    if not worker_id:
        raise ValueError(
            "MORI refuses to schedule an unnamed worker"
        )

    logger.info(
        "MOTH retry scheduler started as %s",
        worker_id,
    )

    while not stop_event.is_set():
        try:
            attempts = await retry_pending_once(
                limit=retry_limit,
                worker_id=worker_id,
            )

            if attempts:
                logger.info(
                    "MOTH retry scheduler processed %d attempt(s)",
                    len(attempts),
                )

        except asyncio.CancelledError:
            raise

        except Exception:
            logger.exception(
                "MORI caught an unexpected retry scheduler failure"
            )

        if stop_event.is_set():
            break

        try:
            await asyncio.wait_for(
                stop_event.wait(),
                timeout=interval_seconds,
            )

        except TimeoutError:
            pass

    logger.info(
        "MOTH retry scheduler stopped"
    )
