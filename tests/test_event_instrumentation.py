import asyncio
import sqlite3

from fastapi.testclient import TestClient

from app import main
from app.api import flags as flags_api
from app.core import retry
from app.core.submitter import (
    SubmissionResult,
)
from app.db import database
from app.db import events


FIRST_FLAG = "FAUST_" + ("M" * 32)
SECOND_FLAG = "FAUST_" + ("N" * 32)


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


def test_single_submission_records_event(
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
                "flag": FIRST_FLAG,
                "service": "achat",
                "source": "pytest",
            },
        )

    assert response.status_code == 200

    recent = events.get_recent_events()

    assert len(recent) == 1

    event = recent[0]

    assert event.event_type == "submission"
    assert event.code == "OK"
    assert event.state == "terminal"
    assert event.service == "achat"
    assert event.source == "pytest"


def test_local_duplicate_records_event(
    test_database,
    monkeypatch,
):
    database.record_submission(
        FIRST_FLAG,
        state=database.TERMINAL_STATE,
        response_code="OK",
    )

    headers = _auth_headers(
        monkeypatch
    )

    with TestClient(main.app) as client:
        response = client.post(
            "/api/flags",
            headers=headers,
            json={
                "flag": FIRST_FLAG,
            },
        )

    assert response.status_code == 200

    recent = events.get_recent_events()

    assert len(recent) == 1
    assert recent[0].event_type == "duplicate"
    assert recent[0].code == "LOCAL"


def test_batch_records_invalid_and_batch_duplicate(
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
            "/api/flags/batch",
            headers=headers,
            json={
                "flags": [
                    FIRST_FLAG,
                    FIRST_FLAG,
                    "not-a-flag",
                ],
            },
        )

    assert response.status_code == 200

    recent = events.get_recent_events()

    assert len(recent) == 3

    observed = {
        (
            event.event_type,
            event.code,
        )
        for event in recent
    }

    assert observed == {
        (
            "submission",
            "OK",
        ),
        (
            "duplicate",
            "BATCH",
        ),
        (
            "invalid",
            "INVALID_FORMAT",
        ),
    }


def test_mori_auth_swat_records_event(
    test_database,
    monkeypatch,
):
    monkeypatch.setenv(
        "MOTH_API_TOKEN",
        "correct-token",
    )

    with TestClient(main.app) as client:
        response = client.get(
            "/api/dashboard/stats"
        )

    assert response.status_code == 401

    recent = events.get_recent_events()

    assert len(recent) == 1

    assert (
        recent[0].event_type
        == "auth_rejected"
    )

    assert recent[0].code == "MISSING"
    assert recent[0].state == "rejected"


def test_retry_worker_records_retry_event(
    test_database,
    monkeypatch,
):
    events.initialize_event_history()

    database.record_submission(
        FIRST_FLAG,
        state=database.RETRYABLE_STATE,
        response_code="ERR",
        response_message="try again later",
        service="achat",
        source="pytest",
    )

    fingerprint = database.fingerprint_flag(
        FIRST_FLAG
    )

    with sqlite3.connect(
        database.DATABASE_PATH
    ) as connection:
        connection.execute(
            """
            UPDATE flags
            SET next_retry_at = ?
            WHERE flag_fingerprint = ?
            """,
            (
                "2000-01-01T00:00:00+00:00",
                fingerprint,
            ),
        )

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
        retry,
        "submit_to_gameserver",
        fake_submit,
    )

    attempts = asyncio.run(
        retry.retry_pending_once(
            worker_id="worker-a",
        )
    )

    assert len(attempts) == 1
    assert attempts[0].recorded is True

    recent = events.get_recent_events()

    assert len(recent) == 1

    event = recent[0]

    assert event.event_type == "retry"
    assert event.code == "OK"
    assert event.state == "terminal"
    assert event.service == "achat"
    assert event.source == "pytest"
    assert event.worker_id == "worker-a"