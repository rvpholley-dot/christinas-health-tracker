"""Tests for GET /log include_deleted (pull sync). Run:
C:\\Python313\\python.exe agent\\test_api.py"""
import os
import sqlite3
import sys
import tempfile
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from fastapi.testclient import TestClient

import api
import create_db

SECRET = "test-secret"
fails = 0


def check(name, cond):
    global fails
    print(("PASS" if cond else "FAIL") + "  " + name)
    if not cond:
        fails += 1


tmp = tempfile.mkdtemp()
db = os.path.join(tmp, "t.db")
create_db.ensure_db(db)
now = datetime.now().strftime("%Y-%m-%dT%H:%M")
conn = sqlite3.connect(db)
conn.execute(
    "INSERT INTO entries (id, category, items, locations, amount, timestamp,"
    " schedule_id, source, notes, created_at, deleted)"
    " VALUES ('a1','water','[\"Light water\"]',NULL,15,?,NULL,'app',NULL,?,0)",
    (now, now))
conn.execute(
    "INSERT INTO entries (id, category, items, locations, amount, timestamp,"
    " schedule_id, source, notes, created_at, deleted)"
    " VALUES ('d1','supplements','[\"Vitamin C\"]',NULL,NULL,?,NULL,'telegram',NULL,?,1)",
    (now, now))
conn.commit()
conn.close()

config = {"db_path": db, "app_shared_secret": SECRET,
          "markdown_dir": os.path.join(tmp, "md")}
client = TestClient(api.create_app(config, {"started_at": "x", "heartbeats": {}}))
H = {"X-CHT-Secret": SECRET}

plain = client.get("/log?days=7", headers=H).json()
withdel = client.get("/log?days=7&include_deleted=1", headers=H).json()

check("default excludes deleted", {e["id"] for e in plain["entries"]} == {"a1"})
check("include_deleted returns both",
      {e["id"] for e in withdel["entries"]} == {"a1", "d1"})
check("tombstone flagged",
      [e for e in withdel["entries"] if e["id"] == "d1"][0]["deleted"] is True)
check("live entry flagged false",
      [e for e in withdel["entries"] if e["id"] == "a1"][0]["deleted"] is False)
check("totals ignore deleted either way",
      plain["totals"] == withdel["totals"]
      and plain["totals"]["waterTodayOz"] == 15)

print("\nFAILURES:", fails)
sys.exit(1 if fails else 0)
