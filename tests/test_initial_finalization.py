"""Verify atomic initial-claim finalization and event-failure resilience."""

import sqlite3

from app.db import (
    database,
    events,
    submission_gate,
)


FIRST_FLAG = "FAUST_" + ("D" * 32)
SECOND_FLAG = "FAUST_" + ("E" * 32)
THIRD_FLAG = "FAUST_" + ("F" * 32)
FOURTH_FLAG = "FAUST_" + ("G" * 32)


def test_terminal_initial_finalization_is_atomic(
    test_database,
):
    claim = (
        submission_gate.claim_initial_submission(
            FIRST_FLAG,
            "worker-a",
        )
    )

    assert claim.status == "claimed"
    assert claim.lease_token is not None

    recorded = (
        submission_gate.finalize_initial_submission(
            FIRST_FLAG,
            "worker-a",
            claim.lease_token,
            state=database.TERMINAL_STATE,
            response_code="OK",
            response_message="accepted",
            service="achat",
            source="pytest",
        )
    )

    assert recorded is True

    record = database.get_submission_record(
        FIRST_FLAG
    )

    assert record is not None
    assert (
        record["submission_state"]
        == database.TERMINAL_STATE
    )
    assert record["response_code"] == "OK"
    assert record["retry_count"] == 0
    assert record["next_retry_at"] is None

    recent = events.get_recent_events()

    assert len(recent) == 1

    event = recent[0]

    assert event.event_type == "submission"
    assert event.code == "OK"
    assert event.state == "terminal"
    assert event.service == "achat"
    assert event.source == "pytest"

    assert (
        submission_gate.release_initial_submission(
            FIRST_FLAG,
            "worker-a",
            claim.lease_token,
        )
        is False
    )

    second_claim = (
        submission_gate.claim_initial_submission(
            FIRST_FLAG,
            "worker-b",
        )
    )

    assert second_claim.status == "existing"
    assert (
        second_claim.existing_state
        == database.TERMINAL_STATE
    )


def test_retryable_initial_finalization_schedules_retry(
    test_database,
):
    claim = (
        submission_gate.claim_initial_submission(
            SECOND_FLAG,
            "worker-a",
        )
    )

    assert claim.status == "claimed"
    assert claim.lease_token is not None

    recorded = (
        submission_gate.finalize_initial_submission(
            SECOND_FLAG,
            "worker-a",
            claim.lease_token,
            state=database.RETRYABLE_STATE,
            response_code="ERR",
            response_message="try again later",
        )
    )

    assert recorded is True

    record = database.get_submission_record(
        SECOND_FLAG
    )

    assert record is not None

    assert (
        record["submission_state"]
        == database.RETRYABLE_STATE
    )

    assert record["response_code"] == "ERR"
    assert record["retry_count"] == 1
    assert record["next_retry_at"] is not None
    assert record["last_attempt_at"] is not None


def test_wrong_initial_claim_token_cannot_finalize(
    test_database,
):
    claim = (
        submission_gate.claim_initial_submission(
            THIRD_FLAG,
            "worker-a",
        )
    )

    assert claim.status == "claimed"
    assert claim.lease_token is not None

    recorded = (
        submission_gate.finalize_initial_submission(
            THIRD_FLAG,
            "worker-a",
            "definitely-not-the-token",
            state=database.TERMINAL_STATE,
            response_code="OK",
        )
    )

    assert recorded is False

    assert (
        database.get_submission_record(
            THIRD_FLAG
        )
        is None
    )

    assert events.get_recent_events() == []

    assert (
        submission_gate.release_initial_submission(
            THIRD_FLAG,
            "worker-a",
            claim.lease_token,
        )
        is True
    )


def test_reclaimed_claim_fences_old_initial_result(
    test_database,
):
    old_claim = (
        submission_gate.claim_initial_submission(
            FOURTH_FLAG,
            "worker-old",
        )
    )

    assert old_claim.status == "claimed"
    assert old_claim.lease_token is not None

    fingerprint = database.fingerprint_flag(
        FOURTH_FLAG
    )

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

    new_claim = (
        submission_gate.claim_initial_submission(
            FOURTH_FLAG,
            "worker-new",
        )
    )

    assert new_claim.status == "claimed"
    assert new_claim.lease_token is not None

    assert (
        new_claim.lease_token
        != old_claim.lease_token
    )

    old_recorded = (
        submission_gate.finalize_initial_submission(
            FOURTH_FLAG,
            "worker-old",
            old_claim.lease_token,
            state=database.TERMINAL_STATE,
            response_code="OK",
        )
    )

    assert old_recorded is False

    assert (
        database.get_submission_record(
            FOURTH_FLAG
        )
        is None
    )

    new_recorded = (
        submission_gate.finalize_initial_submission(
            FOURTH_FLAG,
            "worker-new",
            new_claim.lease_token,
            state=database.TERMINAL_STATE,
            response_code="OK",
        )
    )

    assert new_recorded is True

    record = database.get_submission_record(
        FOURTH_FLAG
    )

    assert record is not None
    assert record["response_code"] == "OK"


def test_event_failure_does_not_lose_submission(
    test_database,
):
    claim = (
        submission_gate.claim_initial_submission(
            FIRST_FLAG,
            "worker-a",
        )
    )

    assert claim.status == "claimed"
    assert claim.lease_token is not None

    with sqlite3.connect(
        database.DATABASE_PATH
    ) as connection:
        connection.execute(
            """
            CREATE TRIGGER fail_submission_event
            BEFORE INSERT ON submission_events
            BEGIN
                SELECT RAISE(
                    ABORT,
                    'scrapbook unavailable'
                );
            END
            """
        )

    recorded = (
        submission_gate.finalize_initial_submission(
            FIRST_FLAG,
            "worker-a",
            claim.lease_token,
            state=database.TERMINAL_STATE,
            response_code="OK",
        )
    )

    assert recorded is True

    record = database.get_submission_record(
        FIRST_FLAG
    )

    assert record is not None
    assert record["response_code"] == "OK"

    assert events.get_recent_events() == []

    assert (
        submission_gate.release_initial_submission(
            FIRST_FLAG,
            "worker-a",
            claim.lease_token,
        )
        is False
    )
