import logging
import secrets
import sqlite3

from dataclasses import dataclass
from datetime import (
    datetime,
    timedelta,
    timezone,
)

from app.core.crypto import (
    encrypt_flag,
    fingerprint_flag,
)

from app.db import database


logger = logging.getLogger(__name__)


DEFAULT_INITIAL_LEASE_SECONDS = 30


@dataclass(
    frozen=True,
    slots=True,
)
class InitialSubmissionClaim:
    status: str
    lease_token: str | None = None
    existing_state: str | None = None


def _utc_now() -> datetime:
    return datetime.now(
        timezone.utc
    )


def initialize_submission_gate() -> None:
    with sqlite3.connect(
        database.DATABASE_PATH
    ) as connection:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS
            initial_submission_claims (
                flag_fingerprint BLOB PRIMARY KEY,
                owner TEXT NOT NULL,
                lease_token TEXT NOT NULL,
                lease_until TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
            """
        )

        connection.execute(
            """
            CREATE INDEX IF NOT EXISTS
            idx_initial_submission_claims_lease_until
            ON initial_submission_claims(
                lease_until
            )
            """
        )


def claim_initial_submission(
    flag: str,
    owner: str,
    *,
    lease_seconds: int = (
        DEFAULT_INITIAL_LEASE_SECONDS
    ),
) -> InitialSubmissionClaim:
    owner = owner.strip()

    if not owner:
        raise ValueError(
            "MORI refuses an unnamed submission worker"
        )

    if lease_seconds <= 0:
        raise ValueError(
            "MORI requires a positive submission lease"
        )

    fingerprint = fingerprint_flag(
        flag
    )

    now = _utc_now()

    now_text = now.isoformat()

    lease_until = (
        now
        + timedelta(
            seconds=lease_seconds
        )
    ).isoformat()

    lease_token = (
        secrets.token_urlsafe(32)
    )

    with sqlite3.connect(
        database.DATABASE_PATH
    ) as connection:
        connection.execute(
            "BEGIN IMMEDIATE"
        )

        existing = connection.execute(
            """
            SELECT submission_state
            FROM flags
            WHERE flag_fingerprint = ?
            """,
            (
                fingerprint,
            ),
        ).fetchone()

        if existing is not None:
            connection.commit()

            return InitialSubmissionClaim(
                status="existing",
                existing_state=existing[0],
            )

        connection.execute(
            """
            DELETE FROM initial_submission_claims
            WHERE
                flag_fingerprint = ?
                AND lease_until <= ?
            """,
            (
                fingerprint,
                now_text,
            ),
        )

        try:
            connection.execute(
                """
                INSERT INTO
                initial_submission_claims (
                    flag_fingerprint,
                    owner,
                    lease_token,
                    lease_until,
                    created_at
                )
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    fingerprint,
                    owner,
                    lease_token,
                    lease_until,
                    now_text,
                ),
            )

        except sqlite3.IntegrityError:
            connection.commit()

            return InitialSubmissionClaim(
                status="busy",
            )

        connection.commit()

    return InitialSubmissionClaim(
        status="claimed",
        lease_token=lease_token,
    )


def finalize_initial_submission(
    flag: str,
    owner: str,
    lease_token: str,
    *,
    state: str,
    response_code: str | None = None,
    response_message: str | None = None,
    service: str | None = None,
    source: str | None = None,
) -> bool:
    if (
        state
        not in database.VALID_SUBMISSION_STATES
    ):
        raise ValueError(
            "mof does not recognize this submission state"
        )

    owner = owner.strip()
    lease_token = lease_token.strip()

    if not owner:
        raise ValueError(
            "MORI refuses results from "
            "an unnamed submission worker"
        )

    if not lease_token:
        raise ValueError(
            "MORI refuses initial results "
            "without a claim token"
        )

    fingerprint = fingerprint_flag(
        flag
    )

    nonce, ciphertext = encrypt_flag(
        flag
    )

    now = _utc_now()
    now_text = now.isoformat()

    if state == database.RETRYABLE_STATE:
        retry_count = 1

        delay = (
            database._retry_delay_seconds(
                retry_count
            )
        )

        next_retry_at = (
            now
            + timedelta(
                seconds=delay
            )
        ).isoformat()

    else:
        retry_count = 0
        next_retry_at = None

    with sqlite3.connect(
        database.DATABASE_PATH,
        isolation_level=None,
    ) as connection:
        connection.execute(
            "BEGIN IMMEDIATE"
        )

        try:
            claim = connection.execute(
                """
                SELECT 1
                FROM initial_submission_claims
                WHERE
                    flag_fingerprint = ?
                    AND owner = ?
                    AND lease_token = ?
                LIMIT 1
                """,
                (
                    fingerprint,
                    owner,
                    lease_token,
                ),
            ).fetchone()

            if claim is None:
                connection.execute(
                    "COMMIT"
                )

                return False

            existing = connection.execute(
                """
                SELECT 1
                FROM flags
                WHERE flag_fingerprint = ?
                LIMIT 1
                """,
                (
                    fingerprint,
                ),
            ).fetchone()

            if existing is not None:
                connection.execute(
                    "COMMIT"
                )

                return False

            result = connection.execute(
                """
                INSERT INTO flags (
                    flag_ciphertext,
                    flag_nonce,
                    flag_fingerprint,
                    submission_state,
                    response_code,
                    response_message,
                    service,
                    source,
                    created_at,
                    updated_at,
                    retry_count,
                    next_retry_at,
                    last_attempt_at,
                    lease_owner,
                    lease_until,
                    lease_token
                )
                VALUES (
                    ?, ?, ?, ?, ?, ?, ?, ?,
                    ?, ?, ?, ?, ?, ?, ?, ?
                )
                """,
                (
                    ciphertext,
                    nonce,
                    fingerprint,
                    state,
                    response_code,
                    response_message,
                    service,
                    source,
                    now_text,
                    now_text,
                    retry_count,
                    next_retry_at,
                    now_text,
                    None,
                    None,
                    None,
                ),
            )

            if result.rowcount != 1:
                connection.execute(
                    "ROLLBACK"
                )

                return False

            connection.execute(
                "SAVEPOINT submission_event"
            )

            try:
                connection.execute(
                    """
                    INSERT INTO submission_events (
                        event_type,
                        code,
                        state,
                        service,
                        source,
                        worker_id,
                        event_count,
                        created_at
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        "submission",
                        response_code,
                        state,
                        service,
                        source,
                        None,
                        1,
                        now_text,
                    ),
                )

            except sqlite3.Error:
                connection.execute(
                    "ROLLBACK TO submission_event"
                )

                logger.exception(
                    "MORI could not write the "
                    "initial submission event "
                    "to the scrapbook"
                )

            finally:
                connection.execute(
                    "RELEASE submission_event"
                )

            released = connection.execute(
                """
                DELETE FROM initial_submission_claims
                WHERE
                    flag_fingerprint = ?
                    AND owner = ?
                    AND lease_token = ?
                """,
                (
                    fingerprint,
                    owner,
                    lease_token,
                ),
            )

            if released.rowcount != 1:
                connection.execute(
                    "ROLLBACK"
                )

                return False

            connection.execute(
                "COMMIT"
            )

            return True

        except Exception:
            connection.execute(
                "ROLLBACK"
            )

            raise


def release_initial_submission(
    flag: str,
    owner: str,
    lease_token: str,
) -> bool:
    fingerprint = fingerprint_flag(
        flag
    )

    with sqlite3.connect(
        database.DATABASE_PATH
    ) as connection:
        cursor = connection.execute(
            """
            DELETE FROM initial_submission_claims
            WHERE
                flag_fingerprint = ?
                AND owner = ?
                AND lease_token = ?
            """,
            (
                fingerprint,
                owner,
                lease_token,
            ),
        )

        return cursor.rowcount == 1