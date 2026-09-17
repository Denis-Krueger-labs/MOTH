import asyncio
import sqlite3

from app.core import retry
from app.core.submitter import (
    SubmissionConnectionError,
    SubmissionResult,
)
from app.db import database


FIRST_FLAG = "FAUST_" + ("T" * 32)
SECOND_FLAG = "FAUST_" + ("U" * 32)
THIRD_FLAG = "FAUST_" + ("V" * 32)


def test_mof_does_not_retry_before_backoff_expires(
    test_database,
    monkeypatch,
):
    clock = {
        "now": "2026-09-17T09:00:00+00:00",
    }

    monkeypatch.setattr(
        database,
        "_utc_now",
        lambda: clock["now"],
    )

    database.record_submission(
        FIRST_FLAG,
        state=database.RETRYABLE_STATE,
        response_code="ERR",
        response_message="try again later",
    )

    clock["now"] = "2026-09-17T09:00:04+00:00"

    async def fake_submit(
        flag: str,
        host: str,
        port: int,
        timeout: float,
    ):
        raise AssertionError(
            "mof should still be waiting"
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

    assert attempts == []

    record = database.get_submission_record(
        FIRST_FLAG
    )

    assert record is not None
    assert record["retry_count"] == 1

    assert (
        record["submission_state"]
        == database.RETRYABLE_STATE
    )


def test_mof_retries_claimed_flag_into_terminal_state(
    test_database,
    monkeypatch,
):
    clock = {
        "now": "2026-09-17T09:00:00+00:00",
    }

    monkeypatch.setattr(
        database,
        "_utc_now",
        lambda: clock["now"],
    )

    database.record_submission(
        FIRST_FLAG,
        state=database.RETRYABLE_STATE,
        response_code="ERR",
        response_message="try again later",
        service="test-service",
        source="pytest",
    )

    clock["now"] = "2026-09-17T09:00:05+00:00"

    async def fake_submit(
        flag: str,
        host: str,
        port: int,
        timeout: float,
    ):
        assert flag == FIRST_FLAG

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

    assert attempts[0].state == database.TERMINAL_STATE
    assert attempts[0].code == "OK"
    assert attempts[0].message == "accepted"
    assert attempts[0].recorded is True

    record = database.get_submission_record(
        FIRST_FLAG
    )

    assert record is not None

    assert (
        record["submission_state"]
        == database.TERMINAL_STATE
    )

    assert record["response_code"] == "OK"

    assert database.has_flag(
        FIRST_FLAG
    ) is True


def test_mof_increases_backoff_after_claimed_retry_fails(
    test_database,
    monkeypatch,
):
    clock = {
        "now": "2026-09-17T09:00:00+00:00",
    }

    monkeypatch.setattr(
        database,
        "_utc_now",
        lambda: clock["now"],
    )

    database.record_submission(
        FIRST_FLAG,
        state=database.RETRYABLE_STATE,
        response_code="ERR",
    )

    clock["now"] = "2026-09-17T09:00:05+00:00"

    async def fake_submit(
        flag: str,
        host: str,
        port: int,
        timeout: float,
    ):
        return SubmissionResult(
            flag=flag,
            code="ERR",
            message="still broken",
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
    assert attempts[0].code == "ERR"
    assert attempts[0].recorded is True

    record = database.get_submission_record(
        FIRST_FLAG
    )

    assert record is not None
    assert record["retry_count"] == 2

    assert (
        record["submission_state"]
        == database.RETRYABLE_STATE
    )

    assert (
        record["next_retry_at"]
        == "2026-09-17T09:00:15+00:00"
    )


def test_one_broken_lamp_does_not_stop_other_claimed_retries(
    test_database,
    monkeypatch,
):
    clock = {
        "now": "2026-09-17T09:00:00+00:00",
    }

    monkeypatch.setattr(
        database,
        "_utc_now",
        lambda: clock["now"],
    )

    database.record_submission(
        FIRST_FLAG,
        state=database.RETRYABLE_STATE,
    )

    database.record_submission(
        SECOND_FLAG,
        state=database.RETRYABLE_STATE,
    )

    clock["now"] = "2026-09-17T09:00:05+00:00"

    async def fake_submit(
        flag: str,
        host: str,
        port: int,
        timeout: float,
    ):
        if flag == FIRST_FLAG:
            raise SubmissionConnectionError(
                "mof could not find the lämp"
            )

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

    assert len(attempts) == 2

    assert (
        attempts[0].state
        == database.RETRYABLE_STATE
    )

    assert (
        attempts[0].code
        == "CONNECTION_ERROR"
    )

    assert attempts[0].recorded is True

    assert (
        attempts[1].state
        == database.TERMINAL_STATE
    )

    assert attempts[1].code == "OK"
    assert attempts[1].recorded is True

    first_record = database.get_submission_record(
        FIRST_FLAG
    )

    second_record = database.get_submission_record(
        SECOND_FLAG
    )

    assert first_record is not None
    assert second_record is not None

    assert (
        first_record["submission_state"]
        == database.RETRYABLE_STATE
    )

    assert first_record["retry_count"] == 2

    assert (
        second_record["submission_state"]
        == database.TERMINAL_STATE
    )


def test_retry_worker_respects_claim_limit(
    test_database,
    monkeypatch,
):
    clock = {
        "now": "2026-09-17T09:00:00+00:00",
    }

    monkeypatch.setattr(
        database,
        "_utc_now",
        lambda: clock["now"],
    )

    for flag in (
        FIRST_FLAG,
        SECOND_FLAG,
        THIRD_FLAG,
    ):
        database.record_submission(
            flag,
            state=database.RETRYABLE_STATE,
            response_code="ERR",
        )

    clock["now"] = "2026-09-17T09:00:05+00:00"

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
            limit=2,
            worker_id="worker-a",
        )
    )

    assert len(attempts) == 2

    assert all(
        attempt.recorded
        for attempt in attempts
    )

    remaining = (
        database.get_due_retryable_submissions()
    )

    assert len(remaining) == 1
    assert remaining[0].flag == THIRD_FLAG


def test_stale_worker_result_is_swatted_and_worker_stops(
    test_database,
    monkeypatch,
):
    clock = {
        "now": "2026-09-17T09:00:00+00:00",
    }

    monkeypatch.setattr(
        database,
        "_utc_now",
        lambda: clock["now"],
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

    clock["now"] = "2026-09-17T09:00:05+00:00"

    replacement_claim = {
        "candidate": None,
    }

    async def fake_submit(
        flag: str,
        host: str,
        port: int,
        timeout: float,
    ):
        assert flag == FIRST_FLAG

        clock["now"] = (
            "2026-09-17T09:00:36+00:00"
        )

        replacement_claim["candidate"] = (
            database.claim_due_retryable_submission(
                "worker-b",
                lease_seconds=30,
            )
        )

        return SubmissionResult(
            flag=flag,
            code="OK",
            message="stale success",
        )

    monkeypatch.setattr(
        retry,
        "submit_to_gameserver",
        fake_submit,
    )

    attempts = asyncio.run(
        retry.retry_pending_once(
            worker_id="worker-a",
            lease_seconds=30,
        )
    )

    assert len(attempts) == 1

    assert attempts[0].code == "OK"
    assert attempts[0].recorded is False

    replacement = replacement_claim[
        "candidate"
    ]

    assert replacement is not None
    assert replacement.flag == FIRST_FLAG
    assert replacement.lease_owner == "worker-b"

    record = database.get_submission_record(
        FIRST_FLAG
    )

    assert record is not None

    assert (
        record["submission_state"]
        == database.RETRYABLE_STATE
    )

    fingerprint = database.fingerprint_flag(
        FIRST_FLAG
    )

    with sqlite3.connect(
        database.DATABASE_PATH
    ) as connection:
        lease = connection.execute(
            """
            SELECT
                lease_owner,
                lease_token
            FROM flags
            WHERE flag_fingerprint = ?
            """,
            (fingerprint,),
        ).fetchone()

    assert lease is not None
    assert lease[0] == "worker-b"
    assert lease[1] == replacement.lease_token

    second_record = database.get_submission_record(
        SECOND_FLAG
    )

    assert second_record is not None

    assert (
        second_record["submission_state"]
        == database.RETRYABLE_STATE
    )