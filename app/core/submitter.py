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