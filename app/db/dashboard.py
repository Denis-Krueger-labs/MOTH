import sqlite3
from datetime import datetime, timezone

from app.db import database


def _utc_now() -> str:
    return datetime.now(
        timezone.utc
    ).isoformat()


def get_dashboard_stats() -> dict[str, object]:
    now = _utc_now()

    with sqlite3.connect(
        database.DATABASE_PATH
    ) as connection:
        connection.row_factory = sqlite3.Row

        totals = connection.execute(
            """
            SELECT
                COUNT(*) AS unique_flags,

                SUM(
                    CASE
                        WHEN submission_state = ?
                        THEN 1
                        ELSE 0
                    END
                ) AS terminal,

                SUM(
                    CASE
                        WHEN submission_state = ?
                        THEN 1
                        ELSE 0
                    END
                ) AS retryable,

                SUM(
                    CASE
                        WHEN response_code = 'OK'
                        THEN 1
                        ELSE 0
                    END
                ) AS accepted,

                SUM(
                    CASE
                        WHEN response_code = 'DUP'
                        THEN 1
                        ELSE 0
                    END
                ) AS gameserver_duplicate,

                SUM(
                    CASE
                        WHEN response_code = 'OWN'
                        THEN 1
                        ELSE 0
                    END
                ) AS own,

                SUM(
                    CASE
                        WHEN response_code = 'OLD'
                        THEN 1
                        ELSE 0
                    END
                ) AS old,

                SUM(
                    CASE
                        WHEN response_code = 'INV'
                        THEN 1
                        ELSE 0
                    END
                ) AS invalid,

                SUM(
                    CASE
                        WHEN submission_state = ?
                         AND lease_until IS NOT NULL
                         AND lease_until > ?
                        THEN 1
                        ELSE 0
                    END
                ) AS active_leases,

                SUM(
                    CASE
                        WHEN submission_state = ?
                         AND (
                                next_retry_at IS NULL
                                OR next_retry_at <= ?
                             )
                         AND (
                                lease_until IS NULL
                                OR lease_until <= ?
                             )
                        THEN 1
                        ELSE 0
                    END
                ) AS due_retries,

                SUM(retry_count) AS retry_count_total
            FROM flags
            """,
            (
                database.TERMINAL_STATE,
                database.RETRYABLE_STATE,
                database.RETRYABLE_STATE,
                now,
                database.RETRYABLE_STATE,
                now,
                now,
            ),
        ).fetchone()

        oldest_retry = connection.execute(
            """
            SELECT MIN(next_retry_at)
            FROM flags
            WHERE submission_state = ?
            """,
            (
                database.RETRYABLE_STATE,
            ),
        ).fetchone()[0]

    return {
        "unique_flags": totals["unique_flags"] or 0,
        "terminal": totals["terminal"] or 0,
        "retryable": totals["retryable"] or 0,
        "accepted": totals["accepted"] or 0,
        "gameserver_duplicate": (
            totals["gameserver_duplicate"] or 0
        ),
        "own": totals["own"] or 0,
        "old": totals["old"] or 0,
        "invalid": totals["invalid"] or 0,
        "active_leases": (
            totals["active_leases"] or 0
        ),
        "due_retries": (
            totals["due_retries"] or 0
        ),
        "retry_count_total": (
            totals["retry_count_total"] or 0
        ),
        "oldest_retry_at": oldest_retry,
    }