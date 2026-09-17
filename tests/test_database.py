import sqlite3

from app.db import database


VALID_FLAG = "FAUST_" + ("R" * 32)


def test_mof_remembers_retryable_submission(
    test_database,
):
    database.record_submission(
        VALID_FLAG,
        state=database.RETRYABLE_STATE,
        response_code="ERR",
        response_message="try again later",
        service="test-service",
        source="pytest",
    )

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
    assert record["service"] == "test-service"
    assert record["source"] == "pytest"

    assert database.has_flag(VALID_FLAG) is False


def test_mof_can_turn_retryable_into_terminal(
    test_database,
    monkeypatch,
):
    timestamps = iter(
        [
            "2026-09-17T06:00:00+00:00",
            "2026-09-17T06:01:00+00:00",
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
        response_message="try again later",
        service="test-service",
        source="pytest",
    )

    first_record = database.get_submission_record(
        VALID_FLAG
    )

    database.record_submission(
        VALID_FLAG,
        state=database.TERMINAL_STATE,
        response_code="OK",
        response_message="accepted",
    )

    second_record = database.get_submission_record(
        VALID_FLAG
    )

    assert first_record is not None
    assert second_record is not None

    assert (
        first_record["created_at"]
        == "2026-09-17T06:00:00+00:00"
    )

    assert (
        second_record["created_at"]
        == "2026-09-17T06:00:00+00:00"
    )

    assert (
        second_record["updated_at"]
        == "2026-09-17T06:01:00+00:00"
    )

    assert (
        second_record["submission_state"]
        == database.TERMINAL_STATE
    )

    assert second_record["response_code"] == "OK"
    assert second_record["service"] == "test-service"
    assert second_record["source"] == "pytest"

    assert database.has_flag(VALID_FLAG) is True


def test_mori_migrates_old_nest_without_eating_it(
    tmp_path,
    monkeypatch,
):
    legacy_database = (
        tmp_path / "legacy_moth.db"
    )

    monkeypatch.setattr(
        database,
        "DATABASE_PATH",
        legacy_database,
    )

    with sqlite3.connect(
        legacy_database
    ) as connection:
        connection.execute(
            """
            CREATE TABLE flags (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                flag_ciphertext BLOB NOT NULL,
                flag_nonce BLOB NOT NULL,
                flag_fingerprint TEXT NOT NULL UNIQUE
            )
            """
        )

    database.initialize_database()

    with sqlite3.connect(
        legacy_database
    ) as connection:
        columns = {
            row[1]
            for row in connection.execute(
                "PRAGMA table_info(flags)"
            ).fetchall()
        }

    assert "submission_state" in columns
    assert "response_code" in columns
    assert "response_message" in columns
    assert "service" in columns
    assert "source" in columns
    assert "created_at" in columns
    assert "updated_at" in columns