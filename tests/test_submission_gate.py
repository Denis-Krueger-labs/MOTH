"""Verify atomic initial-submission claims, release, and recovery behavior."""

import threading
from concurrent.futures import (
    ThreadPoolExecutor,
)

from app.db import database
from app.db import submission_gate


FLAG = "FAUST_" + ("R" * 32)


def test_only_one_initial_claim_wins(
    test_database,
):
    barrier = threading.Barrier(20)

    def claim(index: int):
        barrier.wait()

        return (
            submission_gate
            .claim_initial_submission(
                FLAG,
                f"worker-{index}",
            )
        )

    with ThreadPoolExecutor(
        max_workers=20
    ) as pool:
        results = list(
            pool.map(
                claim,
                range(20),
            )
        )

    claimed = [
        result
        for result in results
        if result.status
        == "claimed"
    ]

    busy = [
        result
        for result in results
        if result.status
        == "busy"
    ]

    assert len(claimed) == 1
    assert len(busy) == 19


def test_existing_terminal_flag_is_not_claimed(
    test_database,
):
    database.record_submission(
        FLAG,
        state=(
            database.TERMINAL_STATE
        ),
        response_code="OK",
    )

    result = (
        submission_gate
        .claim_initial_submission(
            FLAG,
            "worker-a",
        )
    )

    assert (
        result.status
        == "existing"
    )

    assert (
        result.existing_state
        == database.TERMINAL_STATE
    )


def test_existing_retryable_flag_is_not_claimed(
    test_database,
):
    database.record_submission(
        FLAG,
        state=(
            database.RETRYABLE_STATE
        ),
        response_code="ERR",
    )

    result = (
        submission_gate
        .claim_initial_submission(
            FLAG,
            "worker-a",
        )
    )

    assert (
        result.status
        == "existing"
    )

    assert (
        result.existing_state
        == database.RETRYABLE_STATE
    )


def test_release_requires_matching_token(
    test_database,
):
    claim = (
        submission_gate
        .claim_initial_submission(
            FLAG,
            "worker-a",
        )
    )

    assert (
        claim.status
        == "claimed"
    )

    assert (
        claim.lease_token
        is not None
    )

    wrong = (
        submission_gate
        .release_initial_submission(
            FLAG,
            "worker-a",
            "wrong-token",
        )
    )

    assert wrong is False

    correct = (
        submission_gate
        .release_initial_submission(
            FLAG,
            "worker-a",
            claim.lease_token,
        )
    )

    assert correct is True


def test_expired_claim_can_be_recovered(
    test_database,
):
    first = (
        submission_gate
        .claim_initial_submission(
            FLAG,
            "worker-a",
            lease_seconds=1,
        )
    )

    assert (
        first.status
        == "claimed"
    )

    fingerprint = (
        submission_gate
        .fingerprint_flag(
            FLAG
        )
    )

    import sqlite3

    with sqlite3.connect(
        database.DATABASE_PATH
    ) as connection:
        connection.execute(
            """
            UPDATE initial_submission_claims
            SET lease_until = ?
            WHERE flag_fingerprint = ?
            """,
            (
                "2000-01-01T00:00:00+00:00",
                fingerprint,
            ),
        )

    second = (
        submission_gate
        .claim_initial_submission(
            FLAG,
            "worker-b",
        )
    )

    assert (
        second.status
        == "claimed"
    )

    assert (
        second.lease_token
        != first.lease_token
    )
