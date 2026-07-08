"""Create (or idempotently verify) the health-log SQLite database.

Run directly:  python create_db.py [db_path]
Default path:  D:\\Christina\\health-log.db

Timestamps everywhere are local-naive Denver strings ("YYYY-MM-DDTHH:MM"),
matching the PWA's existing localStorage data. Never store UTC.
"""

import sys

import db

DEFAULT_DB_PATH = r"D:\Christina\health-log.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS entries (
  id          TEXT PRIMARY KEY,
  category    TEXT NOT NULL CHECK (category IN
                ('water','supplements','patches','oils','lotion','weight')),
  items       TEXT,               -- JSON array of item names
  locations   TEXT,               -- JSON array [{"item":"X39","location":"back of neck"}]
  amount      REAL,               -- oz for water, lb for weight
  timestamp   TEXT NOT NULL,      -- local-naive "YYYY-MM-DDTHH:MM"
  schedule_id TEXT,
  source      TEXT NOT NULL DEFAULT 'app' CHECK (source IN ('app','telegram')),
  notes       TEXT,
  created_at  TEXT NOT NULL,
  deleted     INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_entries_timestamp ON entries(timestamp);
CREATE INDEX IF NOT EXISTS idx_entries_cat_ts    ON entries(category, timestamp);

-- Mirror of the app's cht.schedule, upserted on /sync.
CREATE TABLE IF NOT EXISTS schedule (
  id         TEXT PRIMARY KEY,
  time       TEXT NOT NULL,       -- "06:30"
  category   TEXT NOT NULL,
  item       TEXT,
  grp        INTEGER NOT NULL DEFAULT 0,
  note       TEXT,
  active     INTEGER NOT NULL DEFAULT 1,
  updated_at TEXT
);

CREATE TABLE IF NOT EXISTS reminders_sent (
  id          INTEGER PRIMARY KEY AUTOINCREMENT,
  schedule_id TEXT NOT NULL,
  due_date    TEXT NOT NULL,      -- "YYYY-MM-DD"
  sent_at     TEXT NOT NULL,
  chat_id     TEXT,
  UNIQUE(schedule_id, due_date)
);

-- Rolling chat memory; the agent loads the last ~20 turns per chat.
CREATE TABLE IF NOT EXISTS conversations (
  id      INTEGER PRIMARY KEY AUTOINCREMENT,
  chat_id TEXT NOT NULL,
  role    TEXT NOT NULL,
  content TEXT NOT NULL,
  ts      TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_conversations_chat ON conversations(chat_id, ts);
"""


def ensure_db(db_path: str = DEFAULT_DB_PATH) -> None:
    conn = db.connect(db_path)
    try:
        conn.execute("PRAGMA journal_mode=WAL")
        conn.executescript(SCHEMA)
        conn.commit()
    finally:
        conn.close()


def main() -> None:
    db_path = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_DB_PATH
    ensure_db(db_path)
    conn = db.connect(db_path)
    try:
        mode = conn.execute("PRAGMA journal_mode").fetchone()[0]
        check = conn.execute("PRAGMA integrity_check").fetchone()[0]
        tables = [r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name")]
    finally:
        conn.close()
    print(f"{db_path}: journal_mode={mode}, integrity_check={check}")
    print(f"tables: {', '.join(tables)}")


if __name__ == "__main__":
    main()
