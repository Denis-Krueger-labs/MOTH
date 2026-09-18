"""Verify dashboard submission and retry statistics."""

import sqlite3

from fastapi.testclient import TestClient

from app import main
from app.api import dashboard as dashboard_api
from app.db import database
from app.db import dashboard


FIRST_FLAG = "FAUST_" + ("J" * 32)
SECOND_FLAG = "FAUST_" + ("K" * 32)
THIRD_FLAG = "FAUST_" + ("L" * 32)


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


def test_dashboard_counts_current_flag_state(
    test_database,
):
    database.record_submission(
        FIRST_FLAG,
        state=database.TERMINAL_STATE,
        response_code="OK",
        response_message="accepted",
    )

    database.record_submission(
        SECOND_FLAG,
        state=database.TERMINAL_STATE,
        response_code="DUP",
        response_message="duplicate",
    )

    database.record_submission(
        THIRD_FLAG,
        state=database.RETRYABLE_STATE,
        response_code="ERR",
        response_message="try again later",
    )

    stats = dashboard.get_dashboard_stats()

    assert stats["unique_flags"] == 3
    assert stats["terminal"] == 2
    assert stats["retryable"] == 1

    assert stats["accepted"] == 1

    assert (
        stats["gameserver_duplicate"]
        == 1
    )

    assert stats["retry_count_total"] == 1

    assert (
        stats["oldest_retry_at"]
        is not None
    )


def test_dashboard_distinguishes_due_and_leased_retries(
    test_database,
    monkeypatch,
):
    monkeypatch.setattr(
        dashboard,
        "_utc_now",
        lambda: (
            "2026-09-17T12:00:00+00:00"
        ),
    )

    database.record_submission(
        FIRST_FLAG,
        state=database.RETRYABLE_STATE,
        response_code="ERR",
    )

    database.record_submission(
        SECOND_FLAG,
        state=database.RETRYABLE_STATE,
        response_code="ERR",
    )

    first_fingerprint = (
        database.fingerprint_flag(
            FIRST_FLAG
        )
    )

    second_fingerprint = (
        database.fingerprint_flag(
            SECOND_FLAG
        )
    )

    with sqlite3.connect(
        database.DATABASE_PATH
    ) as connection:
        connection.execute(
            """
            UPDATE flags
            SET
                next_retry_at = ?,
                lease_owner = NULL,
                lease_until = NULL
            WHERE flag_fingerprint = ?
            """,
            (
                "2026-09-17T11:59:00+00:00",
                first_fingerprint,
            ),
        )

        connection.execute(
            """
            UPDATE flags
            SET
                next_retry_at = ?,
                lease_owner = ?,
                lease_until = ?
            WHERE flag_fingerprint = ?
            """,
            (
                "2026-09-17T11:59:00+00:00",
                "worker-a",
                "2026-09-17T12:01:00+00:00",
                second_fingerprint,
            ),
        )

    stats = dashboard.get_dashboard_stats()

    assert stats["retryable"] == 2
    assert stats["due_retries"] == 1
    assert stats["active_leases"] == 1


def test_dashboard_stats_endpoint_is_authenticated(
    test_database,
    monkeypatch,
):
    expected = {
        "unique_flags": 12,
        "terminal": 10,
        "retryable": 2,
        "accepted": 8,
        "gameserver_duplicate": 1,
        "own": 0,
        "old": 1,
        "invalid": 0,
        "active_leases": 1,
        "due_retries": 1,
        "retry_count_total": 4,
        "oldest_retry_at": (
            "2026-09-17T12:00:00+00:00"
        ),
    }

    monkeypatch.setattr(
        dashboard_api,
        "get_dashboard_stats",
        lambda: expected,
    )

    headers = _auth_headers(
        monkeypatch
    )

    with TestClient(main.app) as client:
        response = client.get(
            "/api/dashboard/stats",
            headers=headers,
        )

    assert response.status_code == 200
    assert response.json() == expected
