import pytest

from app.core.config import (
    get_api_token,
    get_submission_host,
    get_submission_port,
    get_submission_timeout,
)


def test_mof_uses_safe_local_lamp_by_default(
    monkeypatch,
):
    monkeypatch.delenv(
        "MOTH_SUBMISSION_HOST",
        raising=False,
    )
    monkeypatch.delenv(
        "MOTH_SUBMISSION_PORT",
        raising=False,
    )
    monkeypatch.delenv(
        "MOTH_SUBMISSION_TIMEOUT",
        raising=False,
    )

    assert get_submission_host() == "127.0.0.1"
    assert get_submission_port() == 6666
    assert get_submission_timeout() == 5.0


def test_mof_reads_lamp_from_environment(
    monkeypatch,
):
    monkeypatch.setenv(
        "MOTH_SUBMISSION_HOST",
        "fake.gameserver",
    )
    monkeypatch.setenv(
        "MOTH_SUBMISSION_PORT",
        "1234",
    )
    monkeypatch.setenv(
        "MOTH_SUBMISSION_TIMEOUT",
        "2.5",
    )

    assert get_submission_host() == "fake.gameserver"
    assert get_submission_port() == 1234
    assert get_submission_timeout() == 2.5


def test_mof_refuses_suspicious_lamp_port(
    monkeypatch,
):
    monkeypatch.setenv(
        "MOTH_SUBMISSION_PORT",
        "banana",
    )

    with pytest.raises(
        RuntimeError,
        match="must be an integer",
    ):
        get_submission_port()


def test_mof_refuses_suspicious_timeout(
    monkeypatch,
):
    monkeypatch.setenv(
        "MOTH_SUBMISSION_TIMEOUT",
        "0",
    )

    with pytest.raises(
        RuntimeError,
        match="greater than zero",
    ):
        get_submission_timeout()


def test_mori_reads_api_token(
    monkeypatch,
):
    monkeypatch.setenv(
        "MOTH_API_TOKEN",
        "very-secret-moth-token",
    )

    assert (
        get_api_token()
        == "very-secret-moth-token"
    )


def test_mori_refuses_to_guard_without_token(
    monkeypatch,
):
    monkeypatch.delenv(
        "MOTH_API_TOKEN",
        raising=False,
    )

    with pytest.raises(
        RuntimeError,
        match="MOTH_API_TOKEN is missing",
    ):
        get_api_token()