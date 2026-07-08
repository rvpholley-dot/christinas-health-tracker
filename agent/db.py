"""SQLite connection helper for the cht-agent service.

Three loops (HTTP API, Telegram chat, reminders) share one database file,
so every connection gets WAL-friendly settings and a generous busy timeout.
"""

import json
import sqlite3


def connect(db_path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path, timeout=5)
    conn.execute("PRAGMA busy_timeout=5000")
    conn.row_factory = sqlite3.Row
    return conn


def schedule_row_done(row, todays_entries) -> bool:
    """Is this schedule row satisfied by any of today's entries?

    A row counts as done if an entry points at it (schedule_id), or an
    entry of the same category covers it: group rows (patches/oils) and
    item-less rows by category alone, item rows when the item appears in
    the entry's items. Shared by the agent's get_schedule tool and the
    reminder loop so both always agree on "done".
    """
    # tolerate grp arriving as int or text ('0' is truthy in Python!)
    is_group = bool(int(row["grp"] or 0))
    for e in todays_entries:
        if e["schedule_id"] == row["id"]:
            return True
        if e["category"] != row["category"]:
            continue
        if is_group or not row["item"]:
            return True
        items = json.loads(e["items"]) if e["items"] else []
        if row["item"] in items:
            return True
    return False
