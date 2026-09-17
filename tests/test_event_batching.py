import sqlite3

from app.db import database
from app.db import events


def test_pending_swats_are_visible_without_database_writes(
    test_database,
):
    for _ in range(99):
        events.record_batched_event_safely(
            "auth_rejected",
            code="MISSING",
            state="rejected",
            source="api",
        )

    with sqlite3.connect(
        database.DATABASE_PATH
    ) as connection:
        rows = connection.execute(
            """
            SELECT COUNT(*)
            FROM submission_events
            """
        ).fetchone()[0]

    assert rows == 0

    metrics = events.get_event_metrics()

    assert metrics["event_count"] == 99
    assert metrics["mori_swats"] == 99


def test_two_thousand_swats_become_twenty_rows(
    test_database,
):
    for _ in range(2000):
        events.record_batched_event_safely(
            "auth_rejected",
            code="MISSING",
            state="rejected",
            source="api",
        )

    with sqlite3.connect(
        database.DATABASE_PATH
    ) as connection:
        row_count = connection.execute(
            """
            SELECT COUNT(*)
            FROM submission_events
            """
        ).fetchone()[0]

        logical_count = connection.execute(
            """
            SELECT SUM(event_count)
            FROM submission_events
            """
        ).fetchone()[0]

    assert row_count == 20
    assert logical_count == 2000

    metrics = events.get_event_metrics()

    assert metrics["event_count"] == 2000
    assert metrics["mori_swats"] == 2000


def test_shutdown_flush_preserves_partial_batch(
    test_database,
):
    for _ in range(37):
        events.record_batched_event_safely(
            "auth_rejected",
            code="UNKNOWN",
            state="rejected",
            source="api",
        )

    flushed = events.flush_batched_events()

    assert flushed == 37

    recent = events.get_recent_events()

    assert len(recent) == 1

    assert recent[0].event_type == "auth_rejected"
    assert recent[0].code == "UNKNOWN"
    assert recent[0].event_count == 37

    metrics = events.get_event_metrics()

    assert metrics["mori_swats"] == 37