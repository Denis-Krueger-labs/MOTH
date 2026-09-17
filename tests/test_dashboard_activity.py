import sqlite3

from fastapi.testclient import TestClient

from app import main
from app.db import dashboard
from app.db import events


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


def test_event_metrics_count_activity(
    test_database,
    monkeypatch,
):
    events.initialize_event_history()

    monkeypatch.setattr(
        events,
        "_utc_now",
        lambda: (
            "2026-09-17T18:00:30+00:00"
        ),
    )

    events.record_event(
        "submission",
        code="OK",
        state="terminal",
    )

    events.record_event(
        "submission",
        code="ERR",
        state="retryable",
    )

    events.record_event(
        "retry",
        code="OK",
        state="terminal",
    )

    events.record_event(
        "duplicate",
        code="LOCAL",
        state="terminal",
    )

    events.record_event(
        "invalid",
        code="INVALID_FORMAT",
        state="rejected",
    )

    events.record_event(
        "auth_rejected",
        code="MISSING",
        state="rejected",
    )

    events.record_event(
        "retry_stale",
        code="OK",
        state="rejected",
    )

    metrics = events.get_event_metrics()

    assert metrics["event_count"] == 7
    assert metrics["gameserver_attempts"] == 3
    assert metrics["initial_submissions"] == 2
    assert metrics["retry_attempts"] == 1
    assert metrics["local_duplicates"] == 1
    assert metrics["invalid_events"] == 1
    assert metrics["mori_swats"] == 1
    assert metrics["stale_retry_results"] == 1

    assert (
        metrics[
            "initial_submissions_last_minute"
        ]
        == 2
    )

    assert (
        metrics[
            "gameserver_attempts_last_minute"
        ]
        == 3
    )


def test_old_events_are_not_counted_in_last_minute(
    test_database,
    monkeypatch,
):
    events.initialize_event_history()

    with sqlite3.connect(
        events.database.DATABASE_PATH
    ) as connection:
        connection.execute(
            """
            INSERT INTO submission_events (
                event_type,
                code,
                state,
                created_at
            )
            VALUES (?, ?, ?, ?)
            """,
            (
                "submission",
                "OK",
                "terminal",
                "2026-09-17T17:58:00+00:00",
            ),
        )

        connection.execute(
            """
            INSERT INTO submission_events (
                event_type,
                code,
                state,
                created_at
            )
            VALUES (?, ?, ?, ?)
            """,
            (
                "submission",
                "OK",
                "terminal",
                "2026-09-17T17:59:30+00:00",
            ),
        )

    monkeypatch.setattr(
        events,
        "_utc_now",
        lambda: (
            "2026-09-17T18:00:00+00:00"
        ),
    )

    metrics = events.get_event_metrics()

    assert metrics["initial_submissions"] == 2

    assert (
        metrics[
            "initial_submissions_last_minute"
        ]
        == 1
    )


def test_dashboard_stats_include_event_metrics(
    test_database,
):
    events.initialize_event_history()

    events.record_event(
        "submission",
        code="OK",
        state="terminal",
    )

    events.record_event(
        "auth_rejected",
        code="MISSING",
        state="rejected",
    )

    stats = dashboard.get_dashboard_stats()

    assert stats["event_count"] == 2
    assert stats["initial_submissions"] == 1
    assert stats["gameserver_attempts"] == 1
    assert stats["mori_swats"] == 1


def test_recent_activity_endpoint_is_safe(
    test_database,
    monkeypatch,
):
    headers = _auth_headers(
        monkeypatch
    )

    with TestClient(main.app) as client:
        events.record_event(
            "submission",
            code="OK",
            state="terminal",
            service="achat",
            source="pytest",
        )

        response = client.get(
            "/api/dashboard/recent?limit=10",
            headers=headers,
        )

    assert response.status_code == 200

    body = response.json()

    assert body["count"] == 1

    event = body["events"][0]

    assert event["event_type"] == "submission"
    assert event["code"] == "OK"
    assert event["service"] == "achat"
    assert event["source"] == "pytest"
    assert event["event_count"] == 1

    assert set(event) == {
        "id",
        "event_type",
        "code",
        "state",
        "service",
        "source",
        "worker_id",
        "event_count",
        "created_at",
    }

    assert "flag" not in event
    assert "token" not in event
    assert "message" not in event