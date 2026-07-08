"""Missed-dose reminder loop.

Every 5 minutes between 07:00 and 22:00 local (naive wall-clock math —
never UTC): any active schedule row 45+ minutes overdue with no matching
entry today gets nudged on Telegram, exactly once per row per day
(reminders_sent UNIQUE(schedule_id, due_date) is the dedupe). Newly
overdue rows in one pass are combined into a single message so Christina
never gets a burst of pings.

The nudge is also stored as an assistant turn in her conversation memory,
so when she replies "yes, log it" the Phase 2 agent knows what "it" is —
that closes the loop.
"""

import logging
import sqlite3
import time
from datetime import datetime

import agent_llm
import db
import telegram_loop

log = logging.getLogger("cht.reminders")

CHECK_INTERVAL_SECONDS = 300
WINDOW_START_MIN = 7 * 60    # 07:00
WINDOW_END_MIN = 22 * 60     # 22:00 — no nudges after this
OVERDUE_MINUTES = 45


def _to_12h(t: str) -> str:
    h, m = map(int, t.split(":"))
    ap = "AM" if h < 12 else "PM"
    return f"{h % 12 or 12}:{m:02d} {ap}"


def _row_label(row) -> str:
    what = row["item"] or row["category"]
    return f"{_to_12h(row['time'])} {what}"


def _nudge_text(rows) -> str:
    if len(rows) == 1:
        return (f"Gentle nudge 💛 — the {_row_label(rows[0])} isn't logged yet. "
                "Want me to log it?")
    labels = "; ".join(_row_label(r) for r in rows)
    return (f"Gentle nudge 💛 — these aren't logged yet: {labels}. "
            "Want me to log any of them?")


def run_pass(config: dict, now: datetime | None = None) -> int:
    """One reminder sweep; returns how many rows were nudged."""
    now = now or datetime.now()
    minutes = now.hour * 60 + now.minute
    if not (WINDOW_START_MIN <= minutes < WINDOW_END_MIN):
        return 0
    chat_id = config.get("christina_chat_id")
    token = config.get("telegram_bot_token")
    if not chat_id or not token:
        return 0

    today = now.strftime("%Y-%m-%d")
    stamp = now.strftime("%Y-%m-%dT%H:%M")
    due_rows = []

    conn = db.connect(config["db_path"])
    try:
        sched = conn.execute(
            "SELECT * FROM schedule WHERE active=1 ORDER BY time").fetchall()
        todays = conn.execute(
            "SELECT schedule_id, category, items FROM entries WHERE deleted=0 "
            "AND timestamp LIKE ?", (today + "T%",)).fetchall()
        for s in sched:
            h, m = map(int, s["time"].split(":"))
            if minutes - (h * 60 + m) < OVERDUE_MINUTES:
                continue
            if db.schedule_row_done(s, todays):
                continue
            # claim the dedupe slot BEFORE sending — a crash can only lose a
            # nudge, never double-send; a failed send releases the slot below
            try:
                conn.execute(
                    "INSERT INTO reminders_sent (schedule_id, due_date, sent_at, "
                    "chat_id) VALUES (?,?,?,?)",
                    (s["id"], today, stamp, str(chat_id)))
                conn.commit()
            except sqlite3.IntegrityError:
                continue  # already nudged for this row today
            due_rows.append(s)

        if not due_rows:
            return 0

        text = _nudge_text(due_rows)
        try:
            telegram_loop.send_message(token, chat_id, text)
        except Exception:
            log.exception("nudge send failed — releasing slots to retry next pass")
            for s in due_rows:
                conn.execute(
                    "DELETE FROM reminders_sent WHERE schedule_id=? AND due_date=?",
                    (s["id"], today))
            conn.commit()
            return 0
    finally:
        conn.close()

    # give the agent the context, so "yes, log it" makes sense to it
    try:
        agent_llm._store_turn(config, chat_id, "assistant", text)
    except Exception:
        log.exception("could not store nudge in conversation memory")

    log.info("nudged %s about: %s", chat_id,
             "; ".join(_row_label(r) for r in due_rows))
    return len(due_rows)


def run(config: dict, state: dict) -> None:
    log.info("reminder loop starting (07:00-22:00, nudge %s min after "
             "schedule time, every %s s)", OVERDUE_MINUTES, CHECK_INTERVAL_SECONDS)
    if not config.get("christina_chat_id"):
        log.warning("christina_chat_id not set — reminders are disabled")
    while True:
        state["heartbeats"]["reminders"] = time.time()
        try:
            run_pass(config)
        except Exception:
            log.exception("reminder pass failed")
        time.sleep(CHECK_INTERVAL_SECONDS)
