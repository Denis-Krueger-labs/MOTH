import sqlite3
from pathlib import Path
from app.core.crypto import encrypt_flag, fingerprint_flag


DATABASE_PATH = Path("moth.db")


def initialize_database() -> None:
    with sqlite3.connect(DATABASE_PATH) as connection:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS flags (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                flag_ciphertext BLOB NOT NULL,
                flag_nonce BLOB NOT NULL,
                flag_fingerprint TEXT NOT NULL UNIQUE
            )
            """
        )

def store_flag(flag: str) -> bool:
    fingerprint = fingerprint_flag(flag)
    nonce, ciphertext = encrypt_flag(flag)

    try:
        with sqlite3.connect(DATABASE_PATH) as connection:
            connection.execute(
                """
                INSERT INTO flags (
                    flag_ciphertext,
                    flag_nonce,
                    flag_fingerprint
                )
                VALUES (?, ?, ?)
                """,
                (
                    ciphertext,
                    nonce,
                    fingerprint,
                ),
            )

        return True

    except sqlite3.IntegrityError:
        return False