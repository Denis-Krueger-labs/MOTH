"""Verify retry delay calculation and due-retry filtering."""

from app.db import database


VALID_FLAG = "FAUST_" + ("V" * 32)


def test_mof_schedules_first_retry_after_five_seconds(
    test_database,
    monkeypatch,
):
    monkeypatch.setattr(
        database,
        "_utc_now",
        lambda: "2026-09-17T09:00:00+00:00",
    )

    database.record_submission(
        VALID_FLAG,
        state=database.RETRYABLE_STATE,
        response_code="ERR",
        response_message="try again later",
    )

    record = database.get_submission_record(
        VALID_FLAG
    )

    assert record is not None

    assert record["retry_count"] == 1

    assert (
        record["last_attempt_at"]
        == "2026-09-17T09:00:00+00:00"
    )

    assert (
        record["next_retry_at"]
        == "2026-09-17T09:00:05+00:00"
    )


def test_mof_increases_retry_delay(
    test_database,
    monkeypatch,
):
    timestamps = iter(
        [
            "2026-09-17T09:00:00+00:00",
            "2026-09-17T09:01:00+00:00",
            "2026-09-17T09:02:00+00:00",
        ]
    )

    monkeypatch.setattr(
        database,
        "_utc_now",
        lambda: next(timestamps),
    )

    database.record_submission(
        VALID_FLAG,
        state=database.RETRYABLE_STATE,
        response_code="ERR",
    )

    first = database.get_submission_record(
        VALID_FLAG
    )

    database.record_submission(
        VALID_FLAG,
        state=database.RETRYABLE_STATE,
        response_code="ERR",
    )

    second = database.get_submission_record(
        VALID_FLAG
    )

    database.record_submission(
        VALID_FLAG,
        state=database.TERMINAL_STATE,
        response_code="OK",
    )

    terminal = database.get_submission_record(
        VALID_FLAG
    )

    assert first is not None
    assert second is not None
    assert terminal is not None

    assert first["retry_count"] == 1
    assert (
        first["next_retry_at"]
        == "2026-09-17T09:00:05+00:00"
    )

    assert second["retry_count"] == 2
    assert (
        second["next_retry_at"]
        == "2026-09-17T09:01:10+00:00"
    )

    assert terminal["retry_count"] == 2
    assert terminal["next_retry_at"] is None

    assert (
        terminal["created_at"]
        == "2026-09-17T09:00:00+00:00"
    )

    assert (
        terminal["updated_at"]
        == "2026-09-17T09:02:00+00:00"
    )


def test_mof_only_returns_due_retries(
    test_database,
    monkeypatch,
):
    times = iter(
        [
            "2026-09-17T09:00:00+00:00",
            "2026-09-17T09:00:04+00:00",
            "2026-09-17T09:00:05+00:00",
        ]
    )

    monkeypatch.setattr(
        database,
        "_utc_now",
        lambda: next(times),
    )

    database.record_submission(
        VALID_FLAG,
        state=database.RETRYABLE_STATE,
        response_code="ERR",
    )

    not_due = (
        database.get_due_retryable_submissions()
    )

    assert not_due == []

    due = (
        database.get_due_retryable_submissions()
    )

    assert len(due) == 1
    assert due[0].flag == VALID_FLAG
    assert due[0].retry_count == 1
