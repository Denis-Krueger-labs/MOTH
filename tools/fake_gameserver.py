"""Run a small TCP game-server stand-in for local MOTH testing."""

import argparse
import asyncio


async def handle_client(
    reader: asyncio.StreamReader,
    writer: asyncio.StreamWriter,
    *,
    delay_ms: float,
) -> None:
    """Serve one test-protocol connection, optionally delaying its successful reply."""
    peer = writer.get_extra_info("peername")

    try:
        writer.write(
            b"MOTH stress test gameserver\n\n"
        )
        await writer.drain()

        raw_flag = await reader.readline()

        if not raw_flag:
            return

        flag = raw_flag.decode(
            "ascii",
            errors="replace",
        ).strip()

        if delay_ms > 0:
            await asyncio.sleep(
                delay_ms / 1000
            )

        writer.write(
            f"{flag} OK stress-test\n".encode(
                "ascii"
            )
        )

        await writer.drain()

    except Exception as exc:
        print(
            f"client {peer} failed: {exc}"
        )

    finally:
        writer.close()

        try:
            await writer.wait_closed()

        except OSError:
            pass


async def main() -> None:
    """Parse local server options and run the fake game server until interrupted."""
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--port",
        type=int,
        default=6666,
    )

    parser.add_argument(
        "--delay-ms",
        type=float,
        default=0,
    )

    args = parser.parse_args()

    server = await asyncio.start_server(
        lambda reader, writer: handle_client(
            reader,
            writer,
            delay_ms=args.delay_ms,
        ),
        "127.0.0.1",
        args.port,
    )

    print(
        "fake gameserver listening on "
        f"127.0.0.1:{args.port}"
    )

    print(
        f"response delay: {args.delay_ms} ms"
    )

    async with server:
        await server.serve_forever()


if __name__ == "__main__":
    asyncio.run(main())
