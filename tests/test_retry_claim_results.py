import sqlite3

from app.db import database


VALID_FLAG = "FAUST_" + ("R" * 32)


def test_current_lease_owner_can_record_terminal_result(
    test_database,
    monkeypatch,
):
    times = iter(
        [
            "2026-09-17T09:00:00+00:00",
            "2026-09-17T09:00:05+00:00",
            "2026-09-17T09:00:06+00:00",
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

    claimed = (
        database.claim_due_retryable_submission(
            "worker-a",
            lease_seconds=30,
        )
    )

    assert claimed is not None
    assert claimed.lease_token is not None

    written = database.record_claimed_submission(
        VALID_FLAG,
        "worker-a",
        claimed.lease_token,
        state=database.TERMINAL_STATE,
        response_code="OK",
        response_message="accepted",
    )

    assert written is True

    record = database.get_submission_record(
        VALID_FLAG
    )

    assert record is not None
    assert (
        record["submission_state"]
        == database.TERMINAL_STATE
    )
    assert record["response_code"] == "OK"

    assert database.has_flag(
        VALID_FLAG
    ) is True

    fingerprint = database.fingerprint_flag(
        VALID_FLAG
    )

    with sqlite3.connect(
        database.DATABASE_PATH
    ) as connection:
        lease = connection.execute(
            """
            SELECT
                lease_owner,
                lease_until,
                lease_token
            FROM flags
            WHERE flag_fingerprint = ?
            """,
            (fingerprint,),
        ).fetchone()

    assert lease == (
        None,
        None,
        None,
    )


def test_wrong_worker_cannot_record_claimed_result(
    test_database,
    monkeypatch,
):
    times = iter(
        [
            "2026-09-17T09:00:00+00:00",
            "2026-09-17T09:00:05+00:00",
            "2026-09-17T09:00:06+00:00",
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
        response_message="original failure",
    )

    claimed = (
        database.claim_due_retryable_submission(
            "worker-a",
            lease_seconds=30,
        )
    )

    assert claimed is not None
    assert claimed.lease_token is not None

    written = database.record_claimed_submission(
        VALID_FLAG,
        "worker-b",
        claimed.lease_token,
        state=database.TERMINAL_STATE,
        response_code="OK",
        response_message="stolen result",
    )

    assert written is False

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
        == "original failure"
    )


def test_stale_worker_cannot_overwrite_new_owner(
    test_database,
    monkeypatch,
):
    times = iter(
        [
            "2026-09-17T09:00:00+00:00",
            "2026-09-17T09:00:05+00:00",
            "2026-09-17T09:00:36+00:00",
            "2026-09-17T09:00:37+00:00",
            "2026-09-17T09:00:38+00:00",
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

    first_claim = (
        database.claim_due_retryable_submission(
            "worker-a",
            lease_seconds=30,
        )
    )

    assert first_claim is not None
    assert first_claim.lease_token is not None

    second_claim = (
        database.claim_due_retryable_submission(
            "worker-b",
            lease_seconds=30,
        )
    )

    assert second_claim is not None
    assert second_claim.lease_token is not None

    stale_write = (
        database.record_claimed_submission(
            VALID_FLAG,
            "worker-a",
            first_claim.lease_token,
            state=database.TERMINAL_STATE,
            response_code="OK",
            response_message="stale success",
        )
    )

    assert stale_write is False

    current_write = (
        database.record_claimed_submission(
            VALID_FLAG,
            "worker-b",
            second_claim.lease_token,
            state=database.TERMINAL_STATE,
            response_code="OK",
            response_message="current success",
        )
    )

    assert current_write is True

    record = database.get_submission_record(
        VALID_FLAG
    )

    assert record is not None

    assert (
        record["submission_state"]
        == database.TERMINAL_STATE
    )

    assert (
        record["response_message"]
        == "current success"
    )


def test_same_worker_reclaim_gets_new_fencing_token(
    test_database,
    monkeypatch,
):
    times = iter(
        [
            "2026-09-17T09:00:00+00:00",
            "2026-09-17T09:00:05+00:00",
            "2026-09-17T09:00:36+00:00",
            "2026-09-17T09:00:37+00:00",
            "2026-09-17T09:00:38+00:00",
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

    first_claim = (
        database.claim_due_retryable_submission(
            "worker-a",
            lease_seconds=30,
        )
    )

    assert first_claim is not None
    assert first_claim.lease_token is not None

    second_claim = (
        database.claim_due_retryable_submission(
            "worker-a",
            lease_seconds=30,
        )
    )

    assert second_claim is not None
    assert second_claim.lease_token is not None

    assert (
        first_claim.lease_token
        != second_claim.lease_token
    )

    stale_write = (
        database.record_claimed_submission(
            VALID_FLAG,
            "worker-a",
            first_claim.lease_token,
            state=database.TERMINAL_STATE,
            response_code="OK",
            response_message="old incarnation",
        )
    )

    assert stale_write is False

    current_write = (
        database.record_claimed_submission(
            VALID_FLAG,
            "worker-a",
            second_claim.lease_token,
            state=database.TERMINAL_STATE,
            response_code="OK",
            response_message="new incarnation",
        )
    )

    assert current_write is True

    record = database.get_submission_record(
        VALID_FLAG
    )

    assert record is not None

    assert (
        record["response_message"]
        == "new incarnation"
    )


def test_claimed_retry_failure_increases_backoff(
    test_database,
    monkeypatch,
):
    times = iter(
        [
            "2026-09-17T09:00:00+00:00",
            "2026-09-17T09:00:05+00:00",
            "2026-09-17T09:00:06+00:00",
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

    claimed = (
        database.claim_due_retryable_submission(
            "worker-a",
            lease_seconds=30,
        )
    )

    assert claimed is not None
    assert claimed.lease_token is not None
    assert claimed.retry_count == 1

    written = database.record_claimed_submission(
        VALID_FLAG,
        "worker-a",
        claimed.lease_token,
        state=database.RETRYABLE_STATE,
        response_code="ERR",
        response_message="still broken",
    )

    assert written is True

    record = database.get_submission_record(
        VALID_FLAG
    )

    assert record is not None

    assert record["retry_count"] == 2

    assert (
        record["next_retry_at"]
        == "2026-09-17T09:00:16+00:00"
    )

    assert (
        record["submission_state"]
        == database.RETRYABLE_STATE
    )