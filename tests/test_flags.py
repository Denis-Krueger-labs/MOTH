from fastapi.testclient import TestClient

from app import main
from app.api import flags as flags_api
from app.core import submission_service
from app.core.submitter import (
    SubmissionConnectionError,
    SubmissionResult,
    SubmissionTimeoutError,
)
from app.db import database


VALID_FLAG = "FAUST_" + ("A" * 32)
SECOND_VALID_FLAG = "FAUST_" + ("B" * 32)


def _auth_headers(
    monkeypatch,
) -> dict[str, str]:
    token = "test-moth-token"

    monkeypatch.setenv(
        "MOTH_API_TOKEN",
        token,
    )

    return {
        "Authorization": f"Bearer {token}",
    }


def test_mof_accepts_valid_faust_flag_format(
    test_database,
    monkeypatch,
):
    async def fake_submit(
        flag: str,
        host: str,
        port: int,
        timeout: float,
    ):
        return SubmissionResult(
            flag=flag,
            code="OK",
            message="accepted",
        )

    monkeypatch.setattr(
        flags_api,
        "submit_to_gameserver",
        fake_submit,
    )

    headers = _auth_headers(
        monkeypatch
    )

    with TestClient(main.app) as client:
        response = client.post(
            "/api/flags",
            headers=headers,
            json={
                "flag": VALID_FLAG,
            },
        )

    assert response.status_code == 200

    assert response.json() == {
        "status": "submitted",
        "code": "OK",
        "message": "accepted",
        "remembered": True,
    }


def test_mof_rejects_invalid_faust_flag(
    test_database,
    monkeypatch,
):
    headers = _auth_headers(
        monkeypatch
    )

    with TestClient(main.app) as client:
        response = client.post(
            "/api/flags",
            headers=headers,
            json={
                "flag": "definitely-not-a-flag",
            },
        )

    assert response.status_code == 422

    body = response.json()

    assert (
        "mof does not recognize this as a FAUST flag"
        in str(body)
    )


def test_mof_submits_new_flag_and_remembers_it(
    test_database,
    monkeypatch,
):
    flag = VALID_FLAG

    async def fake_submit(
        flag: str,
        host: str,
        port: int,
        timeout: float,
    ):
        assert host == "fake.gameserver"
        assert port == 666
        assert timeout == 2.0

        return SubmissionResult(
            flag=flag,
            code="OK",
            message="accepted",
        )

    monkeypatch.setattr(
        flags_api,
        "submit_to_gameserver",
        fake_submit,
    )

    monkeypatch.setattr(
        submission_service,
        "get_submission_host",
        lambda: "fake.gameserver",
    )

    monkeypatch.setattr(
        submission_service,
        "get_submission_port",
        lambda: 666,
    )

    monkeypatch.setattr(
        submission_service,
        "get_submission_timeout",
        lambda: 2.0,
    )

    headers = _auth_headers(
        monkeypatch
    )

    with TestClient(main.app) as client:
        response = client.post(
            "/api/flags",
            headers=headers,
            json={
                "flag": flag,
                "service": "test-service",
                "source": "pytest",
            },
        )

    assert response.status_code == 200

    assert response.json() == {
        "status": "submitted",
        "code": "OK",
        "message": "accepted",
        "remembered": True,
    }

    record = database.get_submission_record(
        flag
    )

    assert record is not None

    assert (
        record["submission_state"]
        == database.TERMINAL_STATE
    )

    assert record["response_code"] == "OK"
    assert record["response_message"] == "accepted"
    assert record["service"] == "test-service"
    assert record["source"] == "pytest"

    assert database.has_flag(flag) is True


def test_mof_returns_local_duplicate_without_submitting(
    test_database,
    monkeypatch,
):
    database.record_submission(
        VALID_FLAG,
        state=database.TERMINAL_STATE,
        response_code="OK",
        response_message="accepted",
    )

    async def fake_submit(
        flag: str,
        host: str,
        port: int,
        timeout: float,
    ):
        raise AssertionError(
            "duplicate flag reached gameserver"
        )

    monkeypatch.setattr(
        flags_api,
        "submit_to_gameserver",
        fake_submit,
    )

    headers = _auth_headers(
        monkeypatch
    )

    with TestClient(main.app) as client:
        response = client.post(
            "/api/flags",
            headers=headers,
            json={
                "flag": VALID_FLAG,
            },
        )

    assert response.status_code == 200

    assert response.json() == {
        "status": "duplicate",
        "code": "LOCAL",
        "message": (
            "mof has already seen this offering"
        ),
        "remembered": True,
    }


def test_mof_records_err_as_retryable(
    test_database,
    monkeypatch,
):
    async def fake_submit(
        flag: str,
        host: str,
        port: int,
        timeout: float,
    ):
        return SubmissionResult(
            flag=flag,
            code="ERR",
            message="try again later",
        )

    monkeypatch.setattr(
        flags_api,
        "submit_to_gameserver",
        fake_submit,
    )

    headers = _auth_headers(
        monkeypatch
    )

    with TestClient(main.app) as client:
        response = client.post(
            "/api/flags",
            headers=headers,
            json={
                "flag": VALID_FLAG,
                "service": "test-service",
                "source": "pytest",
            },
        )

    assert response.status_code == 200

    assert response.json() == {
        "status": "submitted",
        "code": "ERR",
        "message": "try again later",
        "remembered": False,
    }

    record = database.get_submission_record(
        VALID_FLAG
    )

    assert record is not None

    assert (
        record["submission_state"]
        == database.RETRYABLE_STATE
    )

    assert record["response_code"] == "ERR"

    assert (
        record["response_message"]
        == "try again later"
    )

    assert database.has_flag(
        VALID_FLAG
    ) is False


def test_mof_records_unknown_code_as_retryable(
    test_database,
    monkeypatch,
):
    async def fake_submit(
        flag: str,
        host: str,
        port: int,
        timeout: float,
    ):
        return SubmissionResult(
            flag=flag,
            code="MYSTERY",
            message="moth confusion",
        )

    monkeypatch.setattr(
        flags_api,
        "submit_to_gameserver",
        fake_submit,
    )

    headers = _auth_headers(
        monkeypatch
    )

    with TestClient(main.app) as client:
        response = client.post(
            "/api/flags",
            headers=headers,
            json={
                "flag": VALID_FLAG,
            },
        )

    assert response.status_code == 200

    assert response.json() == {
        "status": "submitted",
        "code": "MYSTERY",
        "message": "moth confusion",
        "remembered": False,
    }

    record = database.get_submission_record(
        VALID_FLAG
    )

    assert record is not None

    assert (
        record["submission_state"]
        == database.RETRYABLE_STATE
    )

    assert (
        record["response_code"]
        == "MYSTERY"
    )


def test_mof_records_timeout_as_retryable(
    test_database,
    monkeypatch,
):
    async def fake_submit(
        flag: str,
        host: str,
        port: int,
        timeout: float,
    ):
        raise SubmissionTimeoutError(
            "mof waited for the lämp, "
            "but it never answered"
        )

    monkeypatch.setattr(
        flags_api,
        "submit_to_gameserver",
        fake_submit,
    )

    headers = _auth_headers(
        monkeypatch
    )

    with TestClient(main.app) as client:
        response = client.post(
            "/api/flags",
            headers=headers,
            json={
                "flag": VALID_FLAG,
            },
        )

    assert response.status_code == 504

    assert response.json() == {
        "detail": (
            "mof waited for the lämp, "
            "but it never answered"
        )
    }

    record = database.get_submission_record(
        VALID_FLAG
    )

    assert record is not None

    assert (
        record["submission_state"]
        == database.RETRYABLE_STATE
    )

    assert (
        record["response_code"]
        == "TIMEOUT"
    )

    assert database.has_flag(
        VALID_FLAG
    ) is False


def test_mof_records_connection_error_as_retryable(
    test_database,
    monkeypatch,
):
    async def fake_submit(
        flag: str,
        host: str,
        port: int,
        timeout: float,
    ):
        raise SubmissionConnectionError(
            "mof flew toward the lämp, "
            "but there was no lämp"
        )

    monkeypatch.setattr(
        flags_api,
        "submit_to_gameserver",
        fake_submit,
    )

    headers = _auth_headers(
        monkeypatch
    )

    with TestClient(main.app) as client:
        response = client.post(
            "/api/flags",
            headers=headers,
            json={
                "flag": VALID_FLAG,
            },
        )

    assert response.status_code == 502

    assert response.json() == {
        "detail": (
            "mof flew toward the lämp, "
            "but there was no lämp"
        )
    }

    record = database.get_submission_record(
        VALID_FLAG
    )

    assert record is not None

    assert (
        record["submission_state"]
        == database.RETRYABLE_STATE
    )

    assert (
        record["response_code"]
        == "CONNECTION_ERROR"
    )

    assert database.has_flag(
        VALID_FLAG
    ) is False