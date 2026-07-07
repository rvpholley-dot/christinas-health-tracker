"""SQLite connection helper for the cht-agent service.

Three loops (HTTP API, Telegram chat, reminders) share one database file,
so every connection gets WAL-friendly settings and a generous busy timeout.
"""

import sqlite3


def connect(db_path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path, timeout=5)
    conn.execute("PRAGMA busy_timeout=5000")
    conn.row_factory = sqlite3.Row
    return conn
