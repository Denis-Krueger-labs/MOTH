import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from app.core.crypto import encrypt_flag, fingerprint_flag


DATABASE_PATH = Path(
    os.getenv("MOTH_DB_PATH", "moth.db")
)

TERMINAL_STATE = "terminal"
RETRYABLE_STATE = "retryable"

VALID_SUBMISSION_STATES = {
    TERMINAL_STATE,
    RETRYABLE_STATE,
}


def _utc_now() -> str:
    return datetime.now(
        timezone.utc
    ).isoformat()


def _get_columns(
    connection: sqlite3.Connection,
) -> set[str]:
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
    }

    for column, statement in migrations.items():
        if column not in columns:
            connection.execute(statement)


def initialize_database() -> None:
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
                updated_at TEXT
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


def has_flag(flag: str) -> bool:
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
                updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)

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
                updated_at = excluded.updated_at
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
                now,
                now,
            ),
        )


def get_submission_record(
    flag: str,
) -> dict[str, str | None] | None:
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
                updated_at
            FROM flags
            WHERE flag_fingerprint = ?
            LIMIT 1
            """,
            (fingerprint,),
        ).fetchone()

    if row is None:
        return None

    return dict(row)


def store_flag(flag: str) -> bool:
    if has_flag(flag):
        return False

    record_submission(
        flag,
        state=TERMINAL_STATE,
    )

    return True