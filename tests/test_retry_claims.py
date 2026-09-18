"""Verify retry claims are exclusive and expired leases can be reclaimed."""

import sqlite3

from app.db import database


VALID_FLAG = "FAUST_" + ("L" * 32)


def test_mori_only_lets_one_worker_claim_retry(
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

    second_claim = (
        database.claim_due_retryable_submission(
            "worker-b",
            lease_seconds=30,
        )
    )

    assert first_claim is not None
    assert first_claim.flag == VALID_FLAG
    assert first_claim.lease_owner == "worker-a"

    assert (
        first_claim.lease_until
        == "2026-09-17T09:00:35+00:00"
    )

    assert second_claim is None


def test_mori_allows_expired_lease_to_be_reclaimed(
    test_database,
    monkeypatch,
):
    times = iter(
        [
            "2026-09-17T09:00:00+00:00",
            "2026-09-17T09:00:05+00:00",
            "2026-09-17T09:00:36+00:00",
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

    second_claim = (
        database.claim_due_retryable_submission(
            "worker-b",
            lease_seconds=30,
        )
    )

    assert first_claim is not None
    assert second_claim is not None

    assert (
        first_claim.id
        == second_claim.id
    )

    assert (
        second_claim.lease_owner
        == "worker-b"
    )

    assert (
        second_claim.lease_until
        == "2026-09-17T09:01:06+00:00"
    )


def test_recording_result_clears_retry_lease(
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
    assert claimed.lease_owner == "worker-a"

    database.record_submission(
        VALID_FLAG,
        state=database.TERMINAL_STATE,
        response_code="OK",
        response_message="accepted",
    )

    fingerprint = database.fingerprint_flag(
        VALID_FLAG
    )

    with sqlite3.connect(
        database.DATABASE_PATH
    ) as connection:
        row = connection.execute(
            """
            SELECT
                lease_owner,
                lease_until
            FROM flags
            WHERE flag_fingerprint = ?
            """,
            (fingerprint,),
        ).fetchone()

    assert row == (
        None,
        None,
    )

    assert database.has_flag(
        VALID_FLAG
    ) is True
