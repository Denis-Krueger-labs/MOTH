from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api import flags as flags_api
from app.core.submitter import (
    SubmissionResult,
    SubmissionTimeoutError,
)


FIRST_FLAG = "FAUST_" + ("A" * 32)
SECOND_FLAG = "FAUST_" + ("B" * 32)
THIRD_FLAG = "FAUST_" + ("C" * 32)


def create_test_client(
    monkeypatch,
) -> TestClient:
    monkeypatch.setenv(
        "MOTH_API_TOKEN",
        "test-token",
    )

    app = FastAPI()
    app.include_router(
        flags_api.router
    )

    return TestClient(app)


def auth_headers() -> dict[str, str]:
    return {
        "Authorization": "Bearer test-token",
    }


def test_batch_submits_multiple_flags(
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

    client = create_test_client(
        monkeypatch
    )

    response = client.post(
        "/api/flags/batch",
        headers=auth_headers(),
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
        "accepted": 2,
        "duplicate": 0,
        "terminal_other": 0,
        "retryable": 0,
        "invalid": 0,
        "in_flight": 0,
        "overloaded": 0,
    }

    assert len(
        body["results"]
    ) == 2

    assert (
        body["results"][0]["code"]
        == "OK"
    )

    assert (
        body["results"][1]["code"]
        == "OK"
    )


def test_batch_deduplicates_inside_request(
    monkeypatch,
):
    calls = 0

    async def fake_submit(
        flag: str,
        host: str,
        port: int,
        timeout: float,
    ):
        nonlocal calls

        calls += 1

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

    client = create_test_client(
        monkeypatch
    )

    response = client.post(
        "/api/flags/batch",
        headers=auth_headers(),
        json={
            "flags": [
                FIRST_FLAG,
                FIRST_FLAG,
            ],
        },
    )

    assert response.status_code == 200

    body = response.json()

    assert body["summary"] == {
        "received": 2,
        "accepted": 1,
        "duplicate": 1,
        "terminal_other": 0,
        "retryable": 0,
        "invalid": 0,
        "in_flight": 0,
        "overloaded": 0,
    }

    assert calls == 1

    assert (
        body["results"][0]["code"]
        == "OK"
    )

    assert (
        body["results"][1]["code"]
        == "BATCH"
    )

    assert (
        body["results"][1]["status"]
        == "duplicate"
    )


def test_batch_invalid_flag_does_not_kill_valid_flag(
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

    client = create_test_client(
        monkeypatch
    )

    response = client.post(
        "/api/flags/batch",
        headers=auth_headers(),
        json={
            "flags": [
                FIRST_FLAG,
                "definitely-not-a-flag",
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
        "in_flight": 0,
        "overloaded": 0,
    }

    assert (
        body["results"][0]["code"]
        == "OK"
    )

    assert (
        body["results"][1]["code"]
        == "INVALID_FORMAT"
    )

    assert (
        body["results"][1]["status"]
        == "invalid"
    )


def test_batch_records_retryable_gameserver_error(
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

    client = create_test_client(
        monkeypatch
    )

    response = client.post(
        "/api/flags/batch",
        headers=auth_headers(),
        json={
            "flags": [
                FIRST_FLAG,
            ],
        },
    )

    assert response.status_code == 200

    body = response.json()

    assert body["summary"] == {
        "received": 1,
        "accepted": 0,
        "duplicate": 0,
        "terminal_other": 0,
        "retryable": 1,
        "invalid": 0,
        "in_flight": 0,
        "overloaded": 0,
    }

    result = body["results"][0]

    assert result["code"] == "ERR"
    assert result["remembered"] is False


def test_batch_timeout_does_not_fail_whole_request(
    monkeypatch,
):
    async def fake_submit(
        flag: str,
        host: str,
        port: int,
        timeout: float,
    ):
        if flag == SECOND_FLAG:
            raise SubmissionTimeoutError(
                "mof waited for the lämp, "
                "but it never answered"
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

    client = create_test_client(
        monkeypatch
    )

    response = client.post(
        "/api/flags/batch",
        headers=auth_headers(),
        json={
            "flags": [
                FIRST_FLAG,
                SECOND_FLAG,
                THIRD_FLAG,
            ],
        },
    )

    assert response.status_code == 200

    body = response.json()

    assert body["summary"] == {
        "received": 3,
        "accepted": 2,
        "duplicate": 0,
        "terminal_other": 0,
        "retryable": 1,
        "invalid": 0,
        "in_flight": 0,
        "overloaded": 0,
    }

    assert (
        body["results"][1]["code"]
        == "TIMEOUT"
    )

    assert (
        body["results"][1]["remembered"]
        is False
    )


def test_batch_refuses_more_than_500_flags(
    monkeypatch,
):
    client = create_test_client(
        monkeypatch
    )

    response = client.post(
        "/api/flags/batch",
        headers=auth_headers(),
        json={
            "flags": [
                FIRST_FLAG
                for _ in range(501)
            ],
        },
    )

    assert response.status_code == 422