import logging
import sqlite3
import threading
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from app.db import database


logger = logging.getLogger(__name__)

MAX_RECENT_EVENTS = 500
DEFAULT_BATCH_SIZE = 100

_BATCH_LOCK = threading.Lock()

_BATCHED_EVENTS: dict[
    tuple[
        str,
        str,
        str | None,
        str | None,
        str | None,
        str | None,
        str | None,
    ],
    int,
] = {}


@dataclass(frozen=True, slots=True)
class SubmissionEvent:
    id: int
    event_type: str
    code: str | None
    state: str | None
    service: str | None
    source: str | None
    worker_id: str | None
    event_count: int
    created_at: str


def _utc_now() -> str:
    return datetime.now(
        timezone.utc
    ).isoformat()


def _database_key() -> str:
    return str(
        database.DATABASE_PATH
    )


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
                event_count INTEGER NOT NULL DEFAULT 1,
                created_at TEXT NOT NULL
            )
            """
        )

        columns = {
            row[1]
            for row in connection.execute(
                """
                PRAGMA table_info(submission_events)
                """
            ).fetchall()
        }

        if "event_count" not in columns:
            connection.execute(
                """
                ALTER TABLE submission_events
                ADD COLUMN event_count
                INTEGER NOT NULL DEFAULT 1
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
    event_count: int = 1,
) -> int:
    event_type = event_type.strip()

    if not event_type:
        raise ValueError(
            "mof refuses to remember an unnamed event"
        )

    if event_count <= 0:
        raise ValueError(
            "mof refuses to remember a non-positive event count"
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
                event_count,
                created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                event_type,
                code,
                state,
                service,
                source,
                worker_id,
                event_count,
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
    event_count: int = 1,
) -> int | None:
    try:
        return record_event(
            event_type,
            code=code,
            state=state,
            service=service,
            source=source,
            worker_id=worker_id,
            event_count=event_count,
        )

    except sqlite3.Error:
        logger.exception(
            "MORI could not write an event to the scrapbook"
        )

        return None


def record_batched_event_safely(
    event_type: str,
    *,
    code: str | None = None,
    state: str | None = None,
    service: str | None = None,
    source: str | None = None,
    worker_id: str | None = None,
    batch_size: int = DEFAULT_BATCH_SIZE,
) -> int | None:
    if batch_size <= 0:
        raise ValueError(
            "mof needs a positive event batch size"
        )

    key = (
        _database_key(),
        event_type,
        code,
        state,
        service,
        source,
        worker_id,
    )

    flush_count = 0

    with _BATCH_LOCK:
        current = (
            _BATCHED_EVENTS.get(
                key,
                0,
            )
            + 1
        )

        if current >= batch_size:
            flush_count = (
                current // batch_size
            ) * batch_size

            remainder = (
                current - flush_count
            )

            if remainder:
                _BATCHED_EVENTS[
                    key
                ] = remainder
            else:
                _BATCHED_EVENTS.pop(
                    key,
                    None,
                )

        else:
            _BATCHED_EVENTS[
                key
            ] = current

    if flush_count == 0:
        return None

    event_id = record_event_safely(
        event_type,
        code=code,
        state=state,
        service=service,
        source=source,
        worker_id=worker_id,
        event_count=flush_count,
    )

    if event_id is None:
        with _BATCH_LOCK:
            _BATCHED_EVENTS[key] = (
                _BATCHED_EVENTS.get(
                    key,
                    0,
                )
                + flush_count
            )

    return event_id


def flush_batched_events() -> int:
    database_key = _database_key()

    pending: list[
        tuple[
            tuple[
                str,
                str,
                str | None,
                str | None,
                str | None,
                str | None,
                str | None,
            ],
            int,
        ]
    ] = []

    with _BATCH_LOCK:
        for key, count in list(
            _BATCHED_EVENTS.items()
        ):
            if key[0] != database_key:
                continue

            pending.append(
                (
                    key,
                    count,
                )
            )

            _BATCHED_EVENTS.pop(
                key,
                None,
            )

    flushed = 0

    for key, count in pending:
        (
            _,
            event_type,
            code,
            state,
            service,
            source,
            worker_id,
        ) = key

        event_id = record_event_safely(
            event_type,
            code=code,
            state=state,
            service=service,
            source=source,
            worker_id=worker_id,
            event_count=count,
        )

        if event_id is None:
            with _BATCH_LOCK:
                _BATCHED_EVENTS[key] = (
                    _BATCHED_EVENTS.get(
                        key,
                        0,
                    )
                    + count
                )

            continue

        flushed += count

    return flushed


def _pending_counts_by_type() -> Counter[str]:
    database_key = _database_key()

    counts: Counter[str] = Counter()

    with _BATCH_LOCK:
        for key, count in (
            _BATCHED_EVENTS.items()
        ):
            if key[0] != database_key:
                continue

            event_type = key[1]

            counts[
                event_type
            ] += count

    return counts


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
                event_count,
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
            event_count=row["event_count"],
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
            metrics = (
                _empty_event_metrics()
            )

        else:
            row = connection.execute(
                """
                SELECT
                    SUM(event_count)
                        AS event_count,

                    SUM(
                        CASE
                            WHEN event_type IN (
                                'submission',
                                'retry'
                            )
                            THEN event_count
                            ELSE 0
                        END
                    ) AS gameserver_attempts,

                    SUM(
                        CASE
                            WHEN event_type = 'submission'
                            THEN event_count
                            ELSE 0
                        END
                    ) AS initial_submissions,

                    SUM(
                        CASE
                            WHEN event_type = 'retry'
                            THEN event_count
                            ELSE 0
                        END
                    ) AS retry_attempts,

                    SUM(
                        CASE
                            WHEN event_type = 'duplicate'
                            THEN event_count
                            ELSE 0
                        END
                    ) AS local_duplicates,

                    SUM(
                        CASE
                            WHEN event_type = 'invalid'
                            THEN event_count
                            ELSE 0
                        END
                    ) AS invalid_events,

                    SUM(
                        CASE
                            WHEN event_type = 'auth_rejected'
                            THEN event_count
                            ELSE 0
                        END
                    ) AS mori_swats,

                    SUM(
                        CASE
                            WHEN event_type = 'retry_stale'
                            THEN event_count
                            ELSE 0
                        END
                    ) AS stale_retry_results,

                    SUM(
                        CASE
                            WHEN event_type = 'submission'
                             AND created_at >= ?
                            THEN event_count
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
                            THEN event_count
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

            metrics = {
                "event_count": (
                    row["event_count"] or 0
                ),
                "gameserver_attempts": (
                    row["gameserver_attempts"]
                    or 0
                ),
                "initial_submissions": (
                    row["initial_submissions"]
                    or 0
                ),
                "retry_attempts": (
                    row["retry_attempts"]
                    or 0
                ),
                "local_duplicates": (
                    row["local_duplicates"]
                    or 0
                ),
                "invalid_events": (
                    row["invalid_events"]
                    or 0
                ),
                "mori_swats": (
                    row["mori_swats"] or 0
                ),
                "stale_retry_results": (
                    row["stale_retry_results"]
                    or 0
                ),
                "initial_submissions_last_minute": (
                    row[
                        "initial_submissions_last_minute"
                    ]
                    or 0
                ),
                "gameserver_attempts_last_minute": (
                    row[
                        "gameserver_attempts_last_minute"
                    ]
                    or 0
                ),
            }

    pending = (
        _pending_counts_by_type()
    )

    pending_total = sum(
        pending.values()
    )

    metrics[
        "event_count"
    ] += pending_total

    metrics[
        "gameserver_attempts"
    ] += (
        pending["submission"]
        + pending["retry"]
    )

    metrics[
        "initial_submissions"
    ] += pending["submission"]

    metrics[
        "retry_attempts"
    ] += pending["retry"]

    metrics[
        "local_duplicates"
    ] += pending["duplicate"]

    metrics[
        "invalid_events"
    ] += pending["invalid"]

    metrics[
        "mori_swats"
    ] += pending["auth_rejected"]

    metrics[
        "stale_retry_results"
    ] += pending["retry_stale"]

    metrics[
        "initial_submissions_last_minute"
    ] += pending["submission"]

    metrics[
        "gameserver_attempts_last_minute"
    ] += (
        pending["submission"]
        + pending["retry"]
    )

    return metrics