"""Verify privacy-safe event history retrieval and validation."""

import sqlite3

import pytest

from app.db import events


def test_mof_records_safe_event_history(
    test_database,
    monkeypatch,
):
    events.initialize_event_history()

    monkeypatch.setattr(
        events,
        "_utc_now",
        lambda: (
            "2026-09-17T18:00:00+00:00"
        ),
    )

    event_id = events.record_event(
        "submission",
        code="OK",
        state="terminal",
        service="achat",
        source="exploit-01",
        worker_id="worker-a",
    )

    assert event_id == 1

    recent = events.get_recent_events()

    assert len(recent) == 1

    event = recent[0]

    assert event.id == 1
    assert event.event_type == "submission"
    assert event.code == "OK"
    assert event.state == "terminal"
    assert event.service == "achat"
    assert event.source == "exploit-01"
    assert event.worker_id == "worker-a"

    assert (
        event.created_at
        == "2026-09-17T18:00:00+00:00"
    )


def test_recent_events_are_newest_first(
    test_database,
    monkeypatch,
):
    events.initialize_event_history()

    timestamps = iter(
        [
            "2026-09-17T18:00:00+00:00",
            "2026-09-17T18:00:01+00:00",
            "2026-09-17T18:00:02+00:00",
        ]
    )

    monkeypatch.setattr(
        events,
        "_utc_now",
        lambda: next(timestamps),
    )

    events.record_event(
        "submission",
        code="ERR",
    )

    events.record_event(
        "retry",
        code="ERR",
    )

    events.record_event(
        "retry",
        code="OK",
    )

    recent = events.get_recent_events(
        limit=2
    )

    assert len(recent) == 2

    assert recent[0].code == "OK"
    assert recent[1].code == "ERR"

    assert recent[0].id == 3
    assert recent[1].id == 2


def test_event_history_contains_no_flag_column(
    test_database,
):
    events.initialize_event_history()

    with sqlite3.connect(
        events.database.DATABASE_PATH
    ) as connection:
        columns = connection.execute(
            """
            PRAGMA table_info(submission_events)
            """
        ).fetchall()

    column_names = {
        row[1]
        for row in columns
    }

    assert "flag" not in column_names
    assert "flag_ciphertext" not in column_names
    assert "flag_fingerprint" not in column_names
    assert "response_message" not in column_names


def test_mof_refuses_bad_event_limits(
    test_database,
):
    events.initialize_event_history()

    with pytest.raises(
        ValueError,
        match="positive event limit",
    ):
        events.get_recent_events(
            limit=0
        )

    with pytest.raises(
        ValueError,
        match="that many event memories",
    ):
        events.get_recent_events(
            limit=501
        )


def test_mof_refuses_unnamed_event(
    test_database,
):
    events.initialize_event_history()

    with pytest.raises(
        ValueError,
        match="unnamed event",
    ):
        events.record_event("   ")
