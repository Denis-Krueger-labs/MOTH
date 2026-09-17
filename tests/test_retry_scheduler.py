import asyncio

import pytest

from app.core import scheduler


def test_scheduler_reuses_one_worker_identity(
    monkeypatch,
):
    worker_ids = []
    stop_event = asyncio.Event()

    async def fake_retry_pending_once(
        limit: int,
        worker_id: str,
    ):
        worker_ids.append(worker_id)

        if len(worker_ids) == 2:
            stop_event.set()

        return []

    monkeypatch.setattr(
        scheduler,
        "retry_pending_once",
        fake_retry_pending_once,
    )

    asyncio.run(
        scheduler.run_retry_scheduler(
            stop_event,
            interval_seconds=0.001,
            worker_id="scheduler-test",
        )
    )

    assert worker_ids == [
        "scheduler-test",
        "scheduler-test",
    ]


def test_scheduler_survives_one_failed_iteration(
    monkeypatch,
):
    calls = 0
    stop_event = asyncio.Event()

    async def fake_retry_pending_once(
        limit: int,
        worker_id: str,
    ):
        nonlocal calls

        calls += 1

        if calls == 1:
            raise RuntimeError(
                "the lämp exploded scientifically"
            )

        stop_event.set()

        return []

    monkeypatch.setattr(
        scheduler,
        "retry_pending_once",
        fake_retry_pending_once,
    )

    asyncio.run(
        scheduler.run_retry_scheduler(
            stop_event,
            interval_seconds=0.001,
            worker_id="scheduler-test",
        )
    )

    assert calls == 2


def test_scheduler_refuses_invalid_configuration():
    async def run_invalid_interval():
        stop_event = asyncio.Event()

        await scheduler.run_retry_scheduler(
            stop_event,
            interval_seconds=0,
        )

    with pytest.raises(
        ValueError,
        match="positive scheduler interval",
    ):
        asyncio.run(
            run_invalid_interval()
        )

    async def run_invalid_limit():
        stop_event = asyncio.Event()

        await scheduler.run_retry_scheduler(
            stop_event,
            retry_limit=0,
        )

    with pytest.raises(
        ValueError,
        match="positive scheduler retry limit",
    ):
        asyncio.run(
            run_invalid_limit()
        )