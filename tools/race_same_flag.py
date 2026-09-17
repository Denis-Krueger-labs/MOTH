import asyncio
import base64
import hashlib
import time
import uuid
from collections import Counter

import httpx

from app.core.config import get_api_token


BASE_URL = "http://127.0.0.1:8000"
HOST = "127.0.0.1"
PORT = 6666


def make_flag() -> str:
    digest = hashlib.sha256(
        uuid.uuid4().bytes
    ).digest()[:24]

    encoded = base64.b64encode(
        digest
    ).decode("ascii")

    return f"FAUST_{encoded}"


class FakeGameServer:
    def __init__(self) -> None:
        self.received: list[str] = []
        self.server = None

    async def handle_client(
        self,
        reader: asyncio.StreamReader,
        writer: asyncio.StreamWriter,
    ) -> None:
        try:
            writer.write(
                b"MOTH duplicate race test\n\n"
            )
            await writer.drain()

            raw_flag = await reader.readline()

            if not raw_flag:
                return

            flag = raw_flag.decode(
                "ascii",
                errors="replace",
            ).strip()

            self.received.append(
                flag
            )

            writer.write(
                f"{flag} OK accepted\n".encode(
                    "ascii"
                )
            )

            await writer.drain()

        finally:
            writer.close()

            try:
                await writer.wait_closed()

            except OSError:
                pass

    async def start(self) -> None:
        self.server = await asyncio.start_server(
            self.handle_client,
            HOST,
            PORT,
        )

    async def stop(self) -> None:
        if self.server is None:
            return

        self.server.close()
        await self.server.wait_closed()


async def main() -> None:
    request_count = 100
    concurrency = 100

    token = get_api_token()
    flag = make_flag()

    fake_server = FakeGameServer()

    await fake_server.start()

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

    async def submit_one(
        client: httpx.AsyncClient,
    ):
        async with semaphore:
            started = time.perf_counter()

            try:
                response = await client.post(
                    "/api/flags",
                    headers={
                        "Authorization": (
                            f"Bearer {token}"
                        )
                    },
                    json={
                        "flag": flag,
                        "service": (
                            "duplicate-race-test"
                        ),
                        "source": (
                            "local-harness"
                        ),
                    },
                )

                elapsed = (
                    time.perf_counter()
                    - started
                )

                body = response.json()

                return (
                    response.status_code,
                    body.get("status"),
                    body.get("code"),
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
                    None,
                    None,
                    elapsed,
                    type(exc).__name__,
                )

    print()
    print("=== SAME-FLAG RACE TEST ===")
    print(
        f"requests: {request_count}"
    )
    print(
        f"concurrency: {concurrency}"
    )
    print(
        "target: localhost only"
    )

    try:
        async with httpx.AsyncClient(
            base_url=BASE_URL,
            limits=limits,
            timeout=timeout,
        ) as client:
            results = await asyncio.gather(
                *[
                    submit_one(client)
                    for _ in range(
                        request_count
                    )
                ]
            )

    finally:
        await fake_server.stop()

    statuses = Counter()
    result_types = Counter()
    codes = Counter()
    errors = Counter()

    for (
        status,
        result_type,
        code,
        _,
        error,
    ) in results:
        if status is not None:
            statuses[status] += 1

        if result_type is not None:
            result_types[
                result_type
            ] += 1

        if code is not None:
            codes[code] += 1

        if error is not None:
            errors[error] += 1

    server_count = len(
        fake_server.received
    )

    unique_server_flags = len(
        set(fake_server.received)
    )

    print()
    print("=== API RESULTS ===")
    print(
        "statuses:",
        dict(statuses),
    )
    print(
        "response statuses:",
        dict(result_types),
    )
    print(
        "codes:",
        dict(codes),
    )
    print(
        "errors:",
        dict(errors),
    )

    print()
    print("=== GAMESERVER IMPACT ===")
    print(
        "TCP submissions received:",
        server_count,
    )
    print(
        "unique flags received:",
        unique_server_flags,
    )

    if server_count == 1:
        print()
        print(
            "PASS: one logical flag caused "
            "exactly one gameserver submission"
        )

    else:
        print()
        print(
            "RACE FOUND: one logical flag caused "
            f"{server_count} gameserver submissions"
        )


if __name__ == "__main__":
    asyncio.run(main())