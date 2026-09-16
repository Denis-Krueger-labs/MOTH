import os

from dotenv import load_dotenv


load_dotenv()


DEFAULT_SUBMISSION_HOST = "127.0.0.1"
DEFAULT_SUBMISSION_PORT = 6666
DEFAULT_SUBMISSION_TIMEOUT = 5.0


def get_submission_host() -> str:
    return os.getenv(
        "MOTH_SUBMISSION_HOST",
        DEFAULT_SUBMISSION_HOST,
    )


def get_submission_port() -> int:
    value = os.getenv(
        "MOTH_SUBMISSION_PORT",
        str(DEFAULT_SUBMISSION_PORT),
    )

    try:
        port = int(value)
    except ValueError as exc:
        raise RuntimeError(
            "MOTH_SUBMISSION_PORT must be an integer"
        ) from exc

    if not 1 <= port <= 65535:
        raise RuntimeError(
            "MOTH_SUBMISSION_PORT must be between 1 and 65535"
        )

    return port


def get_submission_timeout() -> float:
    value = os.getenv(
        "MOTH_SUBMISSION_TIMEOUT",
        str(DEFAULT_SUBMISSION_TIMEOUT),
    )

    try:
        timeout = float(value)
    except ValueError as exc:
        raise RuntimeError(
            "MOTH_SUBMISSION_TIMEOUT must be a number"
        ) from exc

    if timeout <= 0:
        raise RuntimeError(
            "MOTH_SUBMISSION_TIMEOUT must be greater than zero"
        )

    return timeout