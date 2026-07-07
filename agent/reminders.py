"""Missed-dose reminder loop.

Phase 0: heartbeat-only skeleton so /health can watch the thread.
Phase 3 fills in the real logic: every 5 minutes between 07:00-22:00
(local Denver math on naive strings — never UTC), find active schedule rows
45+ minutes overdue with no matching entry today, dedupe via reminders_sent,
and nudge Christina on Telegram.
"""

import logging
import time

log = logging.getLogger("cht.reminders")

CHECK_INTERVAL_SECONDS = 300


def run(config: dict, state: dict) -> None:
    log.info("reminder loop starting (phase 0 skeleton — no nudges yet)")
    while True:
        state["heartbeats"]["reminders"] = time.time()
        try:
            pass  # Phase 3: overdue-schedule check goes here.
        except Exception:
            log.exception("reminder pass failed")
        time.sleep(CHECK_INTERVAL_SECONDS)
