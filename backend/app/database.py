"""Small SQLite helpers. The database file is created on first startup."""

import os
import sqlite3
from contextlib import contextmanager
from pathlib import Path

default_database_path = Path(__file__).resolve().parents[1] / "transcriptions.db"
if os.getenv("VERCEL") == "1":
    default_database_path = Path("/tmp/transcriptions.db")
DATABASE_PATH = Path(os.getenv("DATABASE_PATH", str(default_database_path)))


def connect() -> sqlite3.Connection:
    connection = sqlite3.connect(DATABASE_PATH)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


@contextmanager
def database_session():
    connection = connect()
    try:
        yield connection
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def initialize_database() -> None:
    DATABASE_PATH.parent.mkdir(parents=True, exist_ok=True)
    with database_session() as connection:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS transcriptions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL DEFAULT 'Untitled transcription',
                text TEXT NOT NULL,
                language TEXT NOT NULL DEFAULT 'unknown',
                duration_seconds REAL NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
                updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
            )
            """
        )


def row_to_dict(row: sqlite3.Row) -> dict:
    return dict(row)
