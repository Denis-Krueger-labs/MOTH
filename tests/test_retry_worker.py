import asyncio

from app.core import retry
from app.core.submitter import (
    SubmissionConnectionError,
    SubmissionResult,
)
from app.db import database


FIRST_FLAG = "FAUST_" + ("T" * 32)
SECOND_FLAG = "FAUST_" + ("U" * 32)


def test_mof_does_not_retry_before_backoff_expires(
    test_database,
    monkeypatch,
):
    times = iter(
        [
            "2026-09-17T09:00:00+00:00",
            "2026-09-17T09:00:04+00:00",
        ]
    )

    monkeypatch.setattr(
        database,
        "_utc_now",
        lambda: next(times),
    )

    database.record_submission(
        FIRST_FLAG,
        state=database.RETRYABLE_STATE,
        response_code="ERR",
        response_message="try again later",
    )

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
        retry.retry_pending_once()
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


def test_mof_retries_flag_after_backoff_expires(
    test_database,
    monkeypatch,
):
    times = iter(
        [
            "2026-09-17T09:00:00+00:00",
            "2026-09-17T09:00:05+00:00",
            "2026-09-17T09:00:05+00:00",
        ]
    )

    monkeypatch.setattr(
        database,
        "_utc_now",
        lambda: next(times),
    )

    database.record_submission(
        FIRST_FLAG,
        state=database.RETRYABLE_STATE,
        response_code="ERR",
        response_message="try again later",
        service="test-service",
        source="pytest",
    )

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
        retry.retry_pending_once()
    )

    assert len(attempts) == 1

    assert attempts[0].state == database.TERMINAL_STATE
    assert attempts[0].code == "OK"
    assert attempts[0].message == "accepted"

    record = database.get_submission_record(
        FIRST_FLAG
    )

    assert record is not None
    assert (
        record["submission_state"]
        == database.TERMINAL_STATE
    )
    assert record["response_code"] == "OK"

    assert database.has_flag(FIRST_FLAG) is True


def test_mof_increases_backoff_after_failed_retry(
    test_database,
    monkeypatch,
):
    times = iter(
        [
            "2026-09-17T09:00:00+00:00",
            "2026-09-17T09:00:05+00:00",
            "2026-09-17T09:00:05+00:00",
        ]
    )

    monkeypatch.setattr(
        database,
        "_utc_now",
        lambda: next(times),
    )

    database.record_submission(
        FIRST_FLAG,
        state=database.RETRYABLE_STATE,
        response_code="ERR",
    )

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
        retry.retry_pending_once()
    )

    assert len(attempts) == 1
    assert attempts[0].code == "ERR"

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


def test_one_broken_lamp_does_not_stop_other_retries(
    test_database,
    monkeypatch,
):
    times = iter(
        [
            "2026-09-17T09:00:00+00:00",
            "2026-09-17T09:00:00+00:00",
            "2026-09-17T09:00:05+00:00",
            "2026-09-17T09:00:05+00:00",
            "2026-09-17T09:00:05+00:00",
        ]
    )

    monkeypatch.setattr(
        database,
        "_utc_now",
        lambda: next(times),
    )

    database.record_submission(
        FIRST_FLAG,
        state=database.RETRYABLE_STATE,
    )

    database.record_submission(
        SECOND_FLAG,
        state=database.RETRYABLE_STATE,
    )

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
        retry.retry_pending_once()
    )

    assert len(attempts) == 2

    assert attempts[0].state == database.RETRYABLE_STATE
    assert attempts[0].code == "CONNECTION_ERROR"

    assert attempts[1].state == database.TERMINAL_STATE
    assert attempts[1].code == "OK"

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