from fastapi.testclient import TestClient

from app import main
from app.api import flags as flags_api
from app.core.submitter import (
    SubmissionResult,
    SubmissionTimeoutError,
)
from app.db import database


FIRST_FLAG = "FAUST_" + ("H" * 32)
SECOND_FLAG = "FAUST_" + ("I" * 32)


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


def test_batch_submits_multiple_flags(
    test_database,
    monkeypatch,
):
    submitted = []

    async def fake_submit(
        flag: str,
        host: str,
        port: int,
        timeout: float,
    ):
        submitted.append(flag)

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
            "/api/flags/batch",
            headers=headers,
            json={
                "flags": [
                    FIRST_FLAG,
                    SECOND_FLAG,
                ],
                "service": "achat",
                "source": "pytest",
            },
        )

    assert response.status_code == 200

    body = response.json()

    assert body["summary"] == {
        "received": 2,
        "accepted": 2,
        "duplicate": 0,
        "terminal_other": 0,
        "retryable": 0,
        "invalid": 0,
    }

    assert submitted == [
        FIRST_FLAG,
        SECOND_FLAG,
    ]

    assert (
        database.has_flag(FIRST_FLAG)
        is True
    )

    assert (
        database.has_flag(SECOND_FLAG)
        is True
    )


def test_batch_deduplicates_inside_request(
    test_database,
    monkeypatch,
):
    submitted = []

    async def fake_submit(
        flag: str,
        host: str,
        port: int,
        timeout: float,
    ):
        submitted.append(flag)

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
            "/api/flags/batch",
            headers=headers,
            json={
                "flags": [
                    FIRST_FLAG,
                    FIRST_FLAG,
                ],
            },
        )

    body = response.json()

    assert body["summary"] == {
        "received": 2,
        "accepted": 1,
        "duplicate": 1,
        "terminal_other": 0,
        "retryable": 0,
        "invalid": 0,
    }

    assert submitted == [
        FIRST_FLAG,
    ]

    assert body["results"][1]["code"] == "BATCH"


def test_batch_invalid_flag_does_not_kill_valid_flag(
    test_database,
    monkeypatch,
):
    submitted = []

    async def fake_submit(
        flag: str,
        host: str,
        port: int,
        timeout: float,
    ):
        submitted.append(flag)

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
            "/api/flags/batch",
            headers=headers,
            json={
                "flags": [
                    "not-a-faust-flag",
                    FIRST_FLAG,
                ],
            },
        )

    assert response.status_code == 200

    body = response.json()

    assert body["summary"] == {
        "received": 2,
        "accepted": 1,
        "duplicate": 0,
        "terminal_other": 0,
        "retryable": 0,
        "invalid": 1,
    }

    assert (
        body["results"][0]["status"]
        == "invalid"
    )

    assert submitted == [
        FIRST_FLAG,
    ]


def test_batch_records_retryable_result(
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
            "/api/flags/batch",
            headers=headers,
            json={
                "flags": [
                    FIRST_FLAG,
                ],
            },
        )

    body = response.json()

    assert body["summary"]["retryable"] == 1
    assert body["summary"]["accepted"] == 0

    record = database.get_submission_record(
        FIRST_FLAG
    )

    assert record is not None

    assert (
        record["submission_state"]
        == database.RETRYABLE_STATE
    )


def test_batch_timeout_does_not_fail_whole_request(
    test_database,
    monkeypatch,
):
    async def fake_submit(
        flag: str,
        host: str,
        port: int,
        timeout: float,
    ):
        if flag == FIRST_FLAG:
            raise SubmissionTimeoutError(
                "mof waited for the lämp"
            )

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
            "/api/flags/batch",
            headers=headers,
            json={
                "flags": [
                    FIRST_FLAG,
                    SECOND_FLAG,
                ],
            },
        )

    assert response.status_code == 200

    body = response.json()

    assert body["summary"] == {
        "received": 2,
        "accepted": 1,
        "duplicate": 0,
        "terminal_other": 0,
        "retryable": 1,
        "invalid": 0,
    }

    assert (
        body["results"][0]["code"]
        == "TIMEOUT"
    )

    assert (
        body["results"][1]["code"]
        == "OK"
    )


def test_batch_refuses_more_than_500_flags(
    test_database,
    monkeypatch,
):
    headers = _auth_headers(
        monkeypatch
    )

    flags = [
        FIRST_FLAG
        for _ in range(501)
    ]

    with TestClient(main.app) as client:
        response = client.post(
            "/api/flags/batch",
            headers=headers,
            json={
                "flags": flags,
            },
        )

    assert response.status_code == 422