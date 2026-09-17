import argparse
import asyncio
import base64
import hashlib
import sqlite3
import statistics
import time
import uuid
from collections import Counter
from pathlib import Path

import httpx

from app.core.config import get_api_token
from app.db import database


BASE_URL = "http://127.0.0.1:8000"

MAX_REQUESTS = 20_000
MAX_CONCURRENCY = 250
MAX_BATCH_REQUESTS = 100


def make_flag(
    run_id: str,
    request_id: int,
    item_id: int = 0,
) -> str:
    seed = (
        f"{run_id}:{request_id}:{item_id}"
    ).encode()

    digest = hashlib.sha256(
        seed
    ).digest()[:24]

    encoded = base64.b64encode(
        digest
    ).decode("ascii")

    return f"FAUST_{encoded}"


def percentile(
    values: list[float],
    percentile_value: float,
) -> float:
    if not values:
        return 0.0

    ordered = sorted(values)

    index = round(
        (len(ordered) - 1)
        * percentile_value
    )

    return ordered[index]


def db_snapshot() -> dict[str, int]:
    path = Path(
        database.DATABASE_PATH
    )

    result = {
        "size_bytes": (
            path.stat().st_size
            if path.exists()
            else 0
        ),
        "events": 0,
        "flags": 0,
    }

    if not path.exists():
        return result

    try:
        with sqlite3.connect(
            path,
            timeout=2,
        ) as connection:
            events_table = (
                connection.execute(
                    """
                    SELECT 1
                    FROM sqlite_master
                    WHERE
                        type = 'table'
                        AND name = 'submission_events'
                    """
                ).fetchone()
            )

            if events_table:
                result["events"] = (
                    connection.execute(
                        """
                        SELECT COUNT(*)
                        FROM submission_events
                        """
                    ).fetchone()[0]
                )

            flags_table = (
                connection.execute(
                    """
                    SELECT 1
                    FROM sqlite_master
                    WHERE
                        type = 'table'
                        AND name = 'flags'
                    """
                ).fetchone()
            )

            if flags_table:
                result["flags"] = (
                    connection.execute(
                        """
                        SELECT COUNT(*)
                        FROM flags
                        """
                    ).fetchone()[0]
                )

    except sqlite3.Error:
        pass

    return result


async def perform_request(
    client: httpx.AsyncClient,
    semaphore: asyncio.Semaphore,
    *,
    mode: str,
    request_id: int,
    run_id: str,
    token: str,
    batch_size: int,
) -> tuple[int | None, float, str | None]:
    async with semaphore:
        started = time.perf_counter()

        try:
            if mode == "auth":
                response = await client.get(
                    "/api/dashboard/stats"
                )

            elif mode == "health":
                response = await client.get(
                    "/api/dashboard/health",
                    headers={
                        "Authorization": (
                            f"Bearer {token}"
                        )
                    },
                )

            elif mode == "single":
                response = await client.post(
                    "/api/flags",
                    headers={
                        "Authorization": (
                            f"Bearer {token}"
                        )
                    },
                    json={
                        "flag": make_flag(
                            run_id,
                            request_id,
                        ),
                        "service": (
                            "stress-test"
                        ),
                        "source": (
                            "local-harness"
                        ),
                    },
                )

            elif mode == "batch":
                flags = [
                    make_flag(
                        run_id,
                        request_id,
                        item_id,
                    )
                    for item_id
                    in range(batch_size)
                ]

                response = await client.post(
                    "/api/flags/batch",
                    headers={
                        "Authorization": (
                            f"Bearer {token}"
                        )
                    },
                    json={
                        "flags": flags,
                        "service": (
                            "stress-test"
                        ),
                        "source": (
                            "local-harness"
                        ),
                    },
                )

            else:
                raise RuntimeError(
                    f"unknown mode: {mode}"
                )

            elapsed = (
                time.perf_counter()
                - started
            )

            return (
                response.status_code,
                elapsed,
                None,
            )

        except Exception as exc:
            elapsed = (
                time.perf_counter()
                - started
            )

            return (
                None,
                elapsed,
                type(exc).__name__,
            )


async def run_stress(
    *,
    mode: str,
    requests: int,
    concurrency: int,
    batch_size: int,
) -> None:
    if requests <= 0:
        raise ValueError(
            "requests must be positive"
        )

    if requests > MAX_REQUESTS:
        raise ValueError(
            f"requests may not exceed "
            f"{MAX_REQUESTS}"
        )

    if concurrency <= 0:
        raise ValueError(
            "concurrency must be positive"
        )

    if concurrency > MAX_CONCURRENCY:
        raise ValueError(
            f"concurrency may not exceed "
            f"{MAX_CONCURRENCY}"
        )

    if mode == "batch":
        if requests > MAX_BATCH_REQUESTS:
            raise ValueError(
                "batch mode may not exceed "
                f"{MAX_BATCH_REQUESTS} requests"
            )

        if not 1 <= batch_size <= 500:
            raise ValueError(
                "batch size must be between "
                "1 and 500"
            )

    token = ""

    if mode != "auth":
        token = get_api_token()

    before = db_snapshot()

    run_id = uuid.uuid4().hex

    semaphore = asyncio.Semaphore(
        concurrency
    )

    limits = httpx.Limits(
        max_connections=concurrency,
        max_keepalive_connections=concurrency,
    )

    timeout = httpx.Timeout(
        30.0
    )

    print()
    print("=== MOTH LOCAL STRESS TEST ===")
    print(f"mode: {mode}")
    print(f"requests: {requests}")
    print(f"concurrency: {concurrency}")

    if mode == "batch":
        print(
            f"batch size: {batch_size}"
        )
        print(
            "total offered flags: "
            f"{requests * batch_size}"
        )

    print()
    print(
        "target locked to:",
        BASE_URL,
    )

    started = time.perf_counter()

    async with httpx.AsyncClient(
        base_url=BASE_URL,
        limits=limits,
        timeout=timeout,
    ) as client:
        results = await asyncio.gather(
            *[
                perform_request(
                    client,
                    semaphore,
                    mode=mode,
                    request_id=index,
                    run_id=run_id,
                    token=token,
                    batch_size=batch_size,
                )
                for index
                in range(requests)
            ]
        )

    duration = (
        time.perf_counter()
        - started
    )

    statuses = Counter()
    errors = Counter()
    latencies = []

    for status, elapsed, error in results:
        latencies.append(
            elapsed * 1000
        )

        if status is not None:
            statuses[status] += 1

        if error is not None:
            errors[error] += 1

    after = db_snapshot()

    print()
    print("=== RESULTS ===")
    print(
        f"duration: {duration:.2f}s"
    )

    print(
        "throughput: "
        f"{requests / duration:.2f} req/s"
    )

    print(
        f"mean latency: "
        f"{statistics.mean(latencies):.2f} ms"
    )

    print(
        f"p50 latency: "
        f"{percentile(latencies, 0.50):.2f} ms"
    )

    print(
        f"p95 latency: "
        f"{percentile(latencies, 0.95):.2f} ms"
    )

    print(
        f"p99 latency: "
        f"{percentile(latencies, 0.99):.2f} ms"
    )

    print(
        "statuses:",
        dict(statuses),
    )

    print(
        "errors:",
        dict(errors),
    )

    print()
    print("=== DATABASE IMPACT ===")

    print(
        "event rows:",
        before["events"],
        "->",
        after["events"],
        (
            f"(+{after['events'] - before['events']})"
        ),
    )

    print(
        "flag rows:",
        before["flags"],
        "->",
        after["flags"],
        (
            f"(+{after['flags'] - before['flags']})"
        ),
    )

    size_delta = (
        after["size_bytes"]
        - before["size_bytes"]
    )

    print(
        "database size:",
        before["size_bytes"],
        "->",
        after["size_bytes"],
        "bytes",
    )

    print(
        f"database growth: "
        f"{size_delta / 1024:.2f} KiB"
    )


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Local-only MOTH stress harness"
        )
    )

    parser.add_argument(
        "mode",
        choices=[
            "auth",
            "health",
            "single",
            "batch",
        ],
    )

    parser.add_argument(
        "--requests",
        type=int,
        default=1000,
    )

    parser.add_argument(
        "--concurrency",
        type=int,
        default=50,
    )

    parser.add_argument(
        "--batch-size",
        type=int,
        default=500,
    )

    args = parser.parse_args()

    asyncio.run(
        run_stress(
            mode=args.mode,
            requests=args.requests,
            concurrency=args.concurrency,
            batch_size=args.batch_size,
        )
    )


if __name__ == "__main__":
    main()