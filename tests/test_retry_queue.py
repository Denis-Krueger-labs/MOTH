"""Verify retry-queue ordering, eligibility, and input validation."""

import pytest

from app.db import database


FIRST_FLAG = "FAUST_" + ("Q" * 32)
SECOND_FLAG = "FAUST_" + ("R" * 32)
TERMINAL_FLAG = "FAUST_" + ("S" * 32)


def test_mof_builds_retry_queue_oldest_first(
    test_database,
    monkeypatch,
):
    timestamps = iter(
        [
            "2026-09-17T06:00:00+00:00",
            "2026-09-17T06:01:00+00:00",
            "2026-09-17T06:02:00+00:00",
        ]
    )

    monkeypatch.setattr(
        database,
        "_utc_now",
        lambda: next(timestamps),
    )

    database.record_submission(
        FIRST_FLAG,
        state=database.RETRYABLE_STATE,
        response_code="ERR",
        response_message="first retry",
        service="service-one",
        source="pytest",
    )

    database.record_submission(
        SECOND_FLAG,
        state=database.RETRYABLE_STATE,
        response_code="TIMEOUT",
        response_message="second retry",
        service="service-two",
        source="pytest",
    )

    database.record_submission(
        TERMINAL_FLAG,
        state=database.TERMINAL_STATE,
        response_code="OK",
        response_message="accepted",
    )

    queue = database.get_retryable_submissions()

    assert len(queue) == 2

    assert queue[0].flag == FIRST_FLAG
    assert queue[0].response_code == "ERR"
    assert queue[0].service == "service-one"

    assert queue[1].flag == SECOND_FLAG
    assert queue[1].response_code == "TIMEOUT"
    assert queue[1].service == "service-two"


def test_mof_respects_retry_queue_limit(
    test_database,
):
    database.record_submission(
        FIRST_FLAG,
        state=database.RETRYABLE_STATE,
    )

    database.record_submission(
        SECOND_FLAG,
        state=database.RETRYABLE_STATE,
    )

    queue = database.get_retryable_submissions(
        limit=1,
    )

    assert len(queue) == 1


def test_mof_refuses_nonsense_retry_queue_limit(
    test_database,
):
    with pytest.raises(
        ValueError,
        match="positive retry queue limit",
    ):
        database.get_retryable_submissions(
            limit=0,
        )
