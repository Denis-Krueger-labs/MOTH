import sqlite3
from pathlib import Path


DATABASE_PATH = Path("moth.db")


def initialize_database() -> None:
    with sqlite3.connect(DATABASE_PATH) as connection:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS flags (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                flag TEXT NOT NULL UNIQUE
            )
            """
        )