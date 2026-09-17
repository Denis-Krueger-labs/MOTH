import logging
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from app.db import database


logger = logging.getLogger(__name__)

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


def _empty_event_metrics() -> dict[str, int]:
    return {
        "event_count": 0,
        "gameserver_attempts": 0,
        "initial_submissions": 0,
        "retry_attempts": 0,
        "local_duplicates": 0,
        "invalid_events": 0,
        "mori_swats": 0,
        "stale_retry_results": 0,
        "initial_submissions_last_minute": 0,
        "gameserver_attempts_last_minute": 0,
    }


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


def record_event_safely(
    event_type: str,
    *,
    code: str | None = None,
    state: str | None = None,
    service: str | None = None,
    source: str | None = None,
    worker_id: str | None = None,
) -> int | None:
    try:
        return record_event(
            event_type,
            code=code,
            state=state,
            service=service,
            source=source,
            worker_id=worker_id,
        )

    except sqlite3.Error:
        logger.exception(
            "MORI could not write an event to the scrapbook"
        )

        return None


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


def get_event_metrics() -> dict[str, int]:
    now = datetime.fromisoformat(
        _utc_now()
    )

    minute_ago = (
        now - timedelta(minutes=1)
    ).isoformat()

    with sqlite3.connect(
        database.DATABASE_PATH
    ) as connection:
        connection.row_factory = sqlite3.Row

        table_exists = connection.execute(
            """
            SELECT 1
            FROM sqlite_master
            WHERE
                type = 'table'
                AND name = 'submission_events'
            """
        ).fetchone()

        if table_exists is None:
            return _empty_event_metrics()

        row = connection.execute(
            """
            SELECT
                COUNT(*) AS event_count,

                SUM(
                    CASE
                        WHEN event_type IN (
                            'submission',
                            'retry'
                        )
                        THEN 1
                        ELSE 0
                    END
                ) AS gameserver_attempts,

                SUM(
                    CASE
                        WHEN event_type = 'submission'
                        THEN 1
                        ELSE 0
                    END
                ) AS initial_submissions,

                SUM(
                    CASE
                        WHEN event_type = 'retry'
                        THEN 1
                        ELSE 0
                    END
                ) AS retry_attempts,

                SUM(
                    CASE
                        WHEN event_type = 'duplicate'
                        THEN 1
                        ELSE 0
                    END
                ) AS local_duplicates,

                SUM(
                    CASE
                        WHEN event_type = 'invalid'
                        THEN 1
                        ELSE 0
                    END
                ) AS invalid_events,

                SUM(
                    CASE
                        WHEN event_type = 'auth_rejected'
                        THEN 1
                        ELSE 0
                    END
                ) AS mori_swats,

                SUM(
                    CASE
                        WHEN event_type = 'retry_stale'
                        THEN 1
                        ELSE 0
                    END
                ) AS stale_retry_results,

                SUM(
                    CASE
                        WHEN event_type = 'submission'
                         AND created_at >= ?
                        THEN 1
                        ELSE 0
                    END
                ) AS initial_submissions_last_minute,

                SUM(
                    CASE
                        WHEN event_type IN (
                            'submission',
                            'retry'
                        )
                         AND created_at >= ?
                        THEN 1
                        ELSE 0
                    END
                ) AS gameserver_attempts_last_minute

            FROM submission_events
            """,
            (
                minute_ago,
                minute_ago,
            ),
        ).fetchone()

    return {
        "event_count": row["event_count"] or 0,
        "gameserver_attempts": (
            row["gameserver_attempts"] or 0
        ),
        "initial_submissions": (
            row["initial_submissions"] or 0
        ),
        "retry_attempts": (
            row["retry_attempts"] or 0
        ),
        "local_duplicates": (
            row["local_duplicates"] or 0
        ),
        "invalid_events": (
            row["invalid_events"] or 0
        ),
        "mori_swats": row["mori_swats"] or 0,
        "stale_retry_results": (
            row["stale_retry_results"] or 0
        ),
        "initial_submissions_last_minute": (
            row["initial_submissions_last_minute"]
            or 0
        ),
        "gameserver_attempts_last_minute": (
            row["gameserver_attempts_last_minute"]
            or 0
        ),
    }