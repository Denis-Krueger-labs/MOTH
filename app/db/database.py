"""Persist encrypted flag submissions, retry scheduling, and worker leases."""

import os
import secrets
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

from app.core.crypto import (
    decrypt_flag,
    encrypt_flag,
    fingerprint_flag,
)


DATABASE_PATH = Path(
    os.getenv("MOTH_DB_PATH", "moth.db")
)

TERMINAL_STATE = "terminal"
RETRYABLE_STATE = "retryable"

VALID_SUBMISSION_STATES = {
    TERMINAL_STATE,
    RETRYABLE_STATE,
}

BASE_RETRY_DELAY_SECONDS = 5
MAX_RETRY_DELAY_SECONDS = 300

DEFAULT_RETRY_LEASE_SECONDS = 30


@dataclass
class RetryCandidate:
    """Represent a decrypted retry record together with its worker lease metadata."""

    id: int
    flag: str
    response_code: str | None
    response_message: str | None
    service: str | None
    source: str | None
    created_at: str | None
    updated_at: str | None
    retry_count: int
    next_retry_at: str | None
    last_attempt_at: str | None
    lease_owner: str | None
    lease_until: str | None
    lease_token: str | None


def _utc_now() -> str:
    """Return a sortable, timezone-aware timestamp for persistent records."""
    return datetime.now(
        timezone.utc
    ).isoformat()


def _add_seconds(
    timestamp: str,
    seconds: int,
) -> str:
    """Add a retry or lease duration to an ISO timestamp."""
    value = datetime.fromisoformat(timestamp)

    return (
        value
        + timedelta(seconds=seconds)
    ).isoformat()


def _retry_delay_seconds(
    retry_count: int,
) -> int:
    """Calculate capped exponential backoff for a failed retry attempt."""
    if retry_count <= 0:
        raise ValueError(
            "mof cannot schedule retry number zero"
        )

    delay = (
        BASE_RETRY_DELAY_SECONDS
        * (2 ** (retry_count - 1))
    )

    return min(
        delay,
        MAX_RETRY_DELAY_SECONDS,
    )


def _get_columns(
    connection: sqlite3.Connection,
) -> set[str]:
    """Return existing column names so schema migrations can stay additive."""
    rows = connection.execute(
        "PRAGMA table_info(flags)"
    ).fetchall()

    return {
        row[1]
        for row in rows
    }


def _ensure_columns(
    connection: sqlite3.Connection,
) -> None:
    """Add columns required by newer releases without rebuilding the table."""
    columns = _get_columns(connection)

    migrations = {
        "submission_state": (
            "ALTER TABLE flags "
            "ADD COLUMN submission_state TEXT"
        ),
        "response_code": (
            "ALTER TABLE flags "
            "ADD COLUMN response_code TEXT"
        ),
        "response_message": (
            "ALTER TABLE flags "
            "ADD COLUMN response_message TEXT"
        ),
        "service": (
            "ALTER TABLE flags "
            "ADD COLUMN service TEXT"
        ),
        "source": (
            "ALTER TABLE flags "
            "ADD COLUMN source TEXT"
        ),
        "created_at": (
            "ALTER TABLE flags "
            "ADD COLUMN created_at TEXT"
        ),
        "updated_at": (
            "ALTER TABLE flags "
            "ADD COLUMN updated_at TEXT"
        ),
        "retry_count": (
            "ALTER TABLE flags "
            "ADD COLUMN retry_count "
            "INTEGER NOT NULL DEFAULT 0"
        ),
        "next_retry_at": (
            "ALTER TABLE flags "
            "ADD COLUMN next_retry_at TEXT"
        ),
        "last_attempt_at": (
            "ALTER TABLE flags "
            "ADD COLUMN last_attempt_at TEXT"
        ),
        "lease_owner": (
            "ALTER TABLE flags "
            "ADD COLUMN lease_owner TEXT"
        ),
        "lease_until": (
            "ALTER TABLE flags "
            "ADD COLUMN lease_until TEXT"
        ),
        "lease_token": (
            "ALTER TABLE flags "
            "ADD COLUMN lease_token TEXT"
        ),
    }

    for column, statement in migrations.items():
        if column not in columns:
            connection.execute(statement)


def initialize_database() -> None:
    """Create the submission schema and apply compatible additive migrations."""
    with sqlite3.connect(
        DATABASE_PATH
    ) as connection:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS flags (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                flag_ciphertext BLOB NOT NULL,
                flag_nonce BLOB NOT NULL,
                flag_fingerprint TEXT NOT NULL UNIQUE,
                submission_state TEXT,
                response_code TEXT,
                response_message TEXT,
                service TEXT,
                source TEXT,
                created_at TEXT,
                updated_at TEXT,
                retry_count INTEGER NOT NULL DEFAULT 0,
                next_retry_at TEXT,
                last_attempt_at TEXT,
                lease_owner TEXT,
                lease_until TEXT,
                lease_token TEXT
            )
            """
        )

        _ensure_columns(connection)

        now = _utc_now()

        connection.execute(
            """
            UPDATE flags
            SET submission_state = ?
            WHERE submission_state IS NULL
            """,
            (TERMINAL_STATE,),
        )

        connection.execute(
            """
            UPDATE flags
            SET created_at = ?
            WHERE created_at IS NULL
            """,
            (now,),
        )

        connection.execute(
            """
            UPDATE flags
            SET updated_at = created_at
            WHERE updated_at IS NULL
            """
        )

        connection.execute(
            """
            UPDATE flags
            SET retry_count = 0
            WHERE retry_count IS NULL
            """
        )

        connection.execute(
            """
            UPDATE flags
            SET last_attempt_at = updated_at
            WHERE last_attempt_at IS NULL
              AND updated_at IS NOT NULL
            """
        )

        connection.execute(
            """
            UPDATE flags
            SET next_retry_at = updated_at
            WHERE submission_state = ?
              AND next_retry_at IS NULL
            """,
            (RETRYABLE_STATE,),
        )


def has_flag(flag: str) -> bool:
    """Check whether a flag fingerprint already has a terminal submission record."""
    fingerprint = fingerprint_flag(flag)

    with sqlite3.connect(
        DATABASE_PATH
    ) as connection:
        row = connection.execute(
            """
            SELECT 1
            FROM flags
            WHERE flag_fingerprint = ?
              AND submission_state = ?
            LIMIT 1
            """,
            (
                fingerprint,
                TERMINAL_STATE,
            ),
        ).fetchone()

    return row is not None


def record_submission(
    flag: str,
    *,
    state: str,
    response_code: str | None = None,
    response_message: str | None = None,
    service: str | None = None,
    source: str | None = None,
) -> None:
    """Persist an initial result and schedule another attempt when it is retryable."""
    if state not in VALID_SUBMISSION_STATES:
        raise ValueError(
            "mof does not recognize this submission state"
        )

    fingerprint = fingerprint_flag(flag)
    nonce, ciphertext = encrypt_flag(flag)
    now = _utc_now()

    with sqlite3.connect(
        DATABASE_PATH
    ) as connection:
        connection.row_factory = sqlite3.Row

        existing = connection.execute(
            """
            SELECT
                retry_count,
                created_at
            FROM flags
            WHERE flag_fingerprint = ?
            LIMIT 1
            """,
            (fingerprint,),
        ).fetchone()

        if existing is None:
            previous_retry_count = 0
            created_at = now
        else:
            previous_retry_count = (
                existing["retry_count"] or 0
            )
            created_at = (
                existing["created_at"]
                or now
            )

        if state == RETRYABLE_STATE:
            retry_count = (
                previous_retry_count + 1
            )

            delay = _retry_delay_seconds(
                retry_count
            )

            next_retry_at = _add_seconds(
                now,
                delay,
            )

        else:
            retry_count = previous_retry_count
            next_retry_at = None

        connection.execute(
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
                ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?
            )

            ON CONFLICT(flag_fingerprint)
            DO UPDATE SET
                flag_ciphertext = excluded.flag_ciphertext,
                flag_nonce = excluded.flag_nonce,
                submission_state = excluded.submission_state,
                response_code = excluded.response_code,
                response_message = excluded.response_message,
                service = COALESCE(
                    excluded.service,
                    flags.service
                ),
                source = COALESCE(
                    excluded.source,
                    flags.source
                ),
                updated_at = excluded.updated_at,
                retry_count = excluded.retry_count,
                next_retry_at = excluded.next_retry_at,
                last_attempt_at = excluded.last_attempt_at,
                lease_owner = NULL,
                lease_until = NULL,
                lease_token = NULL
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
                created_at,
                now,
                retry_count,
                next_retry_at,
                now,
                None,
                None,
                None,
            ),
        )


def record_claimed_submission(
    flag: str,
    worker_id: str,
    lease_token: str,
    *,
    state: str,
    response_code: str | None = None,
    response_message: str | None = None,
    service: str | None = None,
    source: str | None = None,
) -> bool:
    """Persist a retry result only when the caller still owns its active lease."""
    if state not in VALID_SUBMISSION_STATES:
        raise ValueError(
            "mof does not recognize this submission state"
        )

    worker_id = worker_id.strip()
    lease_token = lease_token.strip()

    if not worker_id:
        raise ValueError(
            "MORI refuses results from an unnamed worker"
        )

    if not lease_token:
        raise ValueError(
            "MORI refuses results without a lease token"
        )

    fingerprint = fingerprint_flag(flag)
    nonce, ciphertext = encrypt_flag(flag)
    now = _utc_now()

    with sqlite3.connect(
        DATABASE_PATH,
        isolation_level=None,
    ) as connection:
        connection.row_factory = sqlite3.Row

        # Serialize result finalization so an expired lease cannot overwrite a newer claim.
        connection.execute(
            "BEGIN IMMEDIATE"
        )

        try:
            existing = connection.execute(
                """
                SELECT
                    retry_count,
                    created_at,
                    lease_owner,
                    lease_until,
                    lease_token
                FROM flags
                WHERE flag_fingerprint = ?
                  AND submission_state = ?
                  AND lease_owner = ?
                  AND lease_token = ?
                LIMIT 1
                """,
                (
                    fingerprint,
                    RETRYABLE_STATE,
                    worker_id,
                    lease_token,
                ),
            ).fetchone()

            if existing is None:
                connection.execute(
                    "COMMIT"
                )

                return False

            lease_until = existing[
                "lease_until"
            ]

            if (
                lease_until is None
                or lease_until <= now
            ):
                connection.execute(
                    "COMMIT"
                )

                return False

            previous_retry_count = (
                existing["retry_count"] or 0
            )

            created_at = (
                existing["created_at"]
                or now
            )

            if state == RETRYABLE_STATE:
                retry_count = (
                    previous_retry_count + 1
                )

                delay = _retry_delay_seconds(
                    retry_count
                )

                next_retry_at = _add_seconds(
                    now,
                    delay,
                )

            else:
                retry_count = previous_retry_count
                next_retry_at = None

            result = connection.execute(
                """
                UPDATE flags
                SET
                    flag_ciphertext = ?,
                    flag_nonce = ?,
                    submission_state = ?,
                    response_code = ?,
                    response_message = ?,
                    service = COALESCE(
                        ?,
                        service
                    ),
                    source = COALESCE(
                        ?,
                        source
                    ),
                    created_at = ?,
                    updated_at = ?,
                    retry_count = ?,
                    next_retry_at = ?,
                    last_attempt_at = ?,
                    lease_owner = NULL,
                    lease_until = NULL,
                    lease_token = NULL
                WHERE flag_fingerprint = ?
                  AND submission_state = ?
                  AND lease_owner = ?
                  AND lease_token = ?
                  AND lease_until > ?
                """,
                (
                    ciphertext,
                    nonce,
                    state,
                    response_code,
                    response_message,
                    service,
                    source,
                    created_at,
                    now,
                    retry_count,
                    next_retry_at,
                    now,
                    fingerprint,
                    RETRYABLE_STATE,
                    worker_id,
                    lease_token,
                    now,
                ),
            )

            if result.rowcount != 1:
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


def get_submission_record(
    flag: str,
) -> dict[str, str | int | None] | None:
    """Return the safe persisted metadata for a flag, if it exists."""
    fingerprint = fingerprint_flag(flag)

    with sqlite3.connect(
        DATABASE_PATH
    ) as connection:
        connection.row_factory = sqlite3.Row

        row = connection.execute(
            """
            SELECT
                submission_state,
                response_code,
                response_message,
                service,
                source,
                created_at,
                updated_at,
                retry_count,
                next_retry_at,
                last_attempt_at
            FROM flags
            WHERE flag_fingerprint = ?
            LIMIT 1
            """,
            (fingerprint,),
        ).fetchone()

    if row is None:
        return None

    return dict(row)


def _row_to_retry_candidate(
    row: sqlite3.Row,
) -> RetryCandidate:
    """Decrypt one database row into the retry worker's in-memory representation."""
    flag = decrypt_flag(
        row["flag_nonce"],
        row["flag_ciphertext"],
    )

    return RetryCandidate(
        id=row["id"],
        flag=flag,
        response_code=row["response_code"],
        response_message=row["response_message"],
        service=row["service"],
        source=row["source"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
        retry_count=row["retry_count"],
        next_retry_at=row["next_retry_at"],
        last_attempt_at=row["last_attempt_at"],
        lease_owner=row["lease_owner"],
        lease_until=row["lease_until"],
        lease_token=row["lease_token"],
    )


def _rows_to_retry_candidates(
    rows: list[sqlite3.Row],
) -> list[RetryCandidate]:
    """Convert a collection of encrypted rows into retry candidates."""
    return [
        _row_to_retry_candidate(row)
        for row in rows
    ]


def get_retryable_submissions(
    limit: int = 100,
) -> list[RetryCandidate]:
    """Return retryable records in oldest-update order, including leased records."""
    if limit <= 0:
        raise ValueError(
            "mof needs a positive retry queue limit"
        )

    with sqlite3.connect(
        DATABASE_PATH
    ) as connection:
        connection.row_factory = sqlite3.Row

        rows = connection.execute(
            """
            SELECT
                id,
                flag_ciphertext,
                flag_nonce,
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
            FROM flags
            WHERE submission_state = ?
            ORDER BY
                updated_at ASC,
                id ASC
            LIMIT ?
            """,
            (
                RETRYABLE_STATE,
                limit,
            ),
        ).fetchall()

    return _rows_to_retry_candidates(rows)


def get_due_retryable_submissions(
    limit: int = 100,
) -> list[RetryCandidate]:
    """Return retries that are due and unprotected by a current worker lease."""
    if limit <= 0:
        raise ValueError(
            "mof needs a positive retry queue limit"
        )

    now = _utc_now()

    with sqlite3.connect(
        DATABASE_PATH
    ) as connection:
        connection.row_factory = sqlite3.Row

        rows = connection.execute(
            """
            SELECT
                id,
                flag_ciphertext,
                flag_nonce,
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
            FROM flags
            WHERE submission_state = ?
              AND (
                    next_retry_at IS NULL
                    OR next_retry_at <= ?
              )
              AND (
                    lease_until IS NULL
                    OR lease_until <= ?
              )
            ORDER BY
                next_retry_at ASC,
                id ASC
            LIMIT ?
            """,
            (
                RETRYABLE_STATE,
                now,
                now,
                limit,
            ),
        ).fetchall()

    return _rows_to_retry_candidates(rows)


def claim_due_retryable_submission(
    worker_id: str,
    lease_seconds: int = DEFAULT_RETRY_LEASE_SECONDS,
) -> RetryCandidate | None:
    """Atomically lease the oldest due retry and issue a fresh fencing token."""
    worker_id = worker_id.strip()

    if not worker_id:
        raise ValueError(
            "MORI refuses to issue a lease to nobody"
        )

    if lease_seconds <= 0:
        raise ValueError(
            "MORI requires a positive lease duration"
        )

    now = _utc_now()

    lease_until = _add_seconds(
        now,
        lease_seconds,
    )

    lease_token = secrets.token_urlsafe(32)

    with sqlite3.connect(
        DATABASE_PATH,
        isolation_level=None,
    ) as connection:
        connection.row_factory = sqlite3.Row

        # SQLite's write lock makes selecting and leasing one retry atomic across workers.
        connection.execute(
            "BEGIN IMMEDIATE"
        )

        try:
            row = connection.execute(
                """
                SELECT id
                FROM flags
                WHERE submission_state = ?
                  AND (
                        next_retry_at IS NULL
                        OR next_retry_at <= ?
                  )
                  AND (
                        lease_until IS NULL
                        OR lease_until <= ?
                  )
                ORDER BY
                    next_retry_at ASC,
                    id ASC
                LIMIT 1
                """,
                (
                    RETRYABLE_STATE,
                    now,
                    now,
                ),
            ).fetchone()

            if row is None:
                connection.execute(
                    "COMMIT"
                )

                return None

            record_id = row["id"]

            result = connection.execute(
                """
                UPDATE flags
                SET
                    lease_owner = ?,
                    lease_until = ?,
                    lease_token = ?
                WHERE id = ?
                  AND submission_state = ?
                  AND (
                        next_retry_at IS NULL
                        OR next_retry_at <= ?
                  )
                  AND (
                        lease_until IS NULL
                        OR lease_until <= ?
                  )
                """,
                (
                    worker_id,
                    lease_until,
                    lease_token,
                    record_id,
                    RETRYABLE_STATE,
                    now,
                    now,
                ),
            )

            if result.rowcount != 1:
                connection.execute(
                    "ROLLBACK"
                )

                return None

            claimed = connection.execute(
                """
                SELECT
                    id,
                    flag_ciphertext,
                    flag_nonce,
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
                FROM flags
                WHERE id = ?
                LIMIT 1
                """,
                (record_id,),
            ).fetchone()

            connection.execute(
                "COMMIT"
            )

        except Exception:
            connection.execute(
                "ROLLBACK"
            )
            raise

    if claimed is None:
        return None

    return _row_to_retry_candidate(
        claimed
    )


def store_flag(flag: str) -> bool:
    """Store an unseen flag as terminal for callers using the legacy helper."""
    if has_flag(flag):
        return False

    record_submission(
        flag,
        state=TERMINAL_STATE,
    )

    return True
