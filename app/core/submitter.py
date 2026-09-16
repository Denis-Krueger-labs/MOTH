import asyncio
from dataclasses import dataclass


@dataclass
class SubmissionResult:
    flag: str
    code: str
    message: str | None = None


def parse_submission_response(line: str) -> SubmissionResult:
    parts = line.strip().split(maxsplit=2)

    if len(parts) < 2:
        raise ValueError("mof cannot understand the submission response")

    flag = parts[0]
    code = parts[1]
    message = parts[2] if len(parts) == 3 else None

    if not code.isascii() or not code.isalpha() or not code.isupper():
        raise ValueError("mof received a suspicious response code")

    return SubmissionResult(
        flag=flag,
        code=code,
        message=message,
    )


async def submit_flag(
    flag: str,
    host: str,
    port: int,
) -> SubmissionResult:
    reader, writer = await asyncio.open_connection(
        host,
        port,
    )

    try:
        await reader.readuntil(b"\n\n")

        writer.write(
            f"{flag}\n".encode("utf-8")
        )
        await writer.drain()

        response = await reader.readline()

        return parse_submission_response(
            response.decode("utf-8")
        )

    finally:
        writer.close()
        await writer.wait_closed()