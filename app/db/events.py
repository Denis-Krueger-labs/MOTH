import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone

from app.db import database


MAX_RECENT_EVENTS = 500


@dataclass(frozen=True, slots=True)
class SubmissionEvent:
    id: int
    event_type: str
    code: str | None
    state: str | None
    service: str | None
    source: str | None
    worker_id: str | None
    created_at: str


def _utc_now() -> str:
    return datetime.now(
        timezone.utc
    ).isoformat()


def initialize_event_history() -> None:
    with sqlite3.connect(
        database.DATABASE_PATH
    ) as connection:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS submission_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                event_type TEXT NOT NULL,
                code TEXT,
                state TEXT,
                service TEXT,
                source TEXT,
                worker_id TEXT,
                created_at TEXT NOT NULL
            )
            """
        )

        connection.execute(
            """
            CREATE INDEX IF NOT EXISTS
            idx_submission_events_created_at
            ON submission_events(created_at)
            """
        )

        connection.execute(
            """
            CREATE INDEX IF NOT EXISTS
            idx_submission_events_type
            ON submission_events(event_type)
            """
        )


def record_event(
    event_type: str,
    *,
    code: str | None = None,
    state: str | None = None,
    service: str | None = None,
    source: str | None = None,
    worker_id: str | None = None,
) -> int:
    event_type = event_type.strip()

    if not event_type:
        raise ValueError(
            "mof refuses to remember an unnamed event"
        )

    created_at = _utc_now()

    with sqlite3.connect(
        database.DATABASE_PATH
    ) as connection:
        cursor = connection.execute(
            """
            INSERT INTO submission_events (
                event_type,
                code,
                state,
                service,
                source,
                worker_id,
                created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                event_type,
                code,
                state,
                service,
                source,
                worker_id,
                created_at,
            ),
        )

        event_id = cursor.lastrowid

    if event_id is None:
        raise RuntimeError(
            "mof failed to remember the event"
        )

    return event_id


def get_recent_events(
    limit: int = 50,
) -> list[SubmissionEvent]:
    if limit <= 0:
        raise ValueError(
            "mof needs a positive event limit"
        )

    if limit > MAX_RECENT_EVENTS:
        raise ValueError(
            "mof refuses to carry that many event memories at once"
        )

    with sqlite3.connect(
        database.DATABASE_PATH
    ) as connection:
        connection.row_factory = sqlite3.Row

        rows = connection.execute(
            """
            SELECT
                id,
                event_type,
                code,
                state,
                service,
                source,
                worker_id,
                created_at
            FROM submission_events
            ORDER BY
                created_at DESC,
                id DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()

    return [
        SubmissionEvent(
            id=row["id"],
            event_type=row["event_type"],
            code=row["code"],
            state=row["state"],
            service=row["service"],
            source=row["source"],
            worker_id=row["worker_id"],
            created_at=row["created_at"],
        )
        for row in rows
    ]