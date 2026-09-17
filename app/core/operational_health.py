import asyncio
from time import perf_counter

from fastapi import FastAPI

from app.core.config import (
    get_submission_host,
    get_submission_port,
    get_submission_timeout,
)


def get_scheduler_status(
    app: FastAPI,
) -> dict[str, object]:
    task = getattr(
        app.state,
        "retry_scheduler_task",
        None,
    )

    stop_event = getattr(
        app.state,
        "retry_scheduler_stop_event",
        None,
    )

    if task is None:
        state = "unknown"
        running = False

    elif task.cancelled():
        state = "stopped"
        running = False

    elif task.done():
        state = "stopped"
        running = False

    elif (
        stop_event is not None
        and stop_event.is_set()
    ):
        state = "stopping"
        running = True

    else:
        state = "running"
        running = True

    return {
        "state": state,
        "running": running,
    }


def build_operational_health(
    app: FastAPI,
    stats: dict[str, object],
) -> dict[str, object]:
    scheduler = get_scheduler_status(
        app
    )

    retryable = int(
        stats["retryable"]
    )

    due_retries = int(
        stats["due_retries"]
    )

    active_leases = int(
        stats["active_leases"]
    )

    if retryable == 0:
        queue_state = "clear"

    elif active_leases > 0:
        queue_state = "working"

    elif due_retries > 0:
        queue_state = "backlogged"

    else:
        queue_state = "waiting"

    if scheduler["running"]:
        overall_status = "healthy"

    else:
        overall_status = "degraded"

    return {
        "status": overall_status,
        "scheduler": scheduler,
        "retry_queue": {
            "state": queue_state,
            "retryable": retryable,
            "due": due_retries,
            "active_leases": active_leases,
            "oldest_retry_at": (
                stats["oldest_retry_at"]
            ),
        },
    }


async def probe_submission_server() -> (
    dict[str, object]
):
    try:
        host = get_submission_host()
        port = get_submission_port()
        timeout = get_submission_timeout()

    except RuntimeError:
        return {
            "status": "misconfigured",
            "reachable": False,
            "host": None,
            "port": None,
            "latency_ms": None,
            "greeting_received": False,
        }

    started = perf_counter()
    writer = None

    try:
        reader, writer = await asyncio.wait_for(
            asyncio.open_connection(
                host,
                port,
            ),
            timeout=timeout,
        )

        greeting = await asyncio.wait_for(
            reader.readuntil(
                b"\n\n"
            ),
            timeout=timeout,
        )

        latency_ms = round(
            (
                perf_counter()
                - started
            )
            * 1000,
            2,
        )

        return {
            "status": "reachable",
            "reachable": True,
            "host": host,
            "port": port,
            "latency_ms": latency_ms,
            "greeting_received": True,
            "greeting_bytes": len(
                greeting
            ),
        }

    except TimeoutError:
        return {
            "status": "timeout",
            "reachable": False,
            "host": host,
            "port": port,
            "latency_ms": None,
            "greeting_received": False,
        }

    except (
        ConnectionError,
        OSError,
    ):
        return {
            "status": "unreachable",
            "reachable": False,
            "host": host,
            "port": port,
            "latency_ms": None,
            "greeting_received": False,
        }

    except (
        asyncio.IncompleteReadError,
        asyncio.LimitOverrunError,
    ):
        return {
            "status": "protocol_error",
            "reachable": True,
            "host": host,
            "port": port,
            "latency_ms": None,
            "greeting_received": False,
        }

    finally:
        if writer is not None:
            writer.close()

            try:
                await writer.wait_closed()

            except (
                ConnectionError,
                OSError,
            ):
                pass