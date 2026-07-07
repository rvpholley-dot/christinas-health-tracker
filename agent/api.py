"""HTTP API for the tracker PWA, served on 127.0.0.1:8765 behind
`tailscale serve --https=8446` (tailnet-only, never public).

Endpoints (all JSON):
  GET  /health — liveness + background-loop heartbeats (no secret needed)
  POST /sync   — push-up sync from the app: upsert entries by id, mirror the
                 schedule, re-render the daily markdown. Idempotent, so the
                 app can retry and backfill freely.
  GET  /log    — entries + computed totals for the app's Log view.

/sync and /log require the X-CHT-Secret header (401 on mismatch). CORS is
locked to the GitHub Pages origin; Safari preflights the custom header, so
the middleware must answer OPTIONS.
"""

import hmac
import json
import logging
import re
import time
from datetime import datetime, timedelta

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware

import db
import render_md

log = logging.getLogger("cht.api")

CATEGORIES = {"water", "supplements", "patches", "oils", "lotion", "weight"}
TS_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}")

ALLOWED_ORIGINS = [
    "https://rvpholley-dot.github.io",
    "http://localhost:8000",  # local testing per README; secret still required
]


def _clean_entry(e):
    """Validate one incoming entry; returns a normalized dict or None."""
    if not isinstance(e, dict):
        return None
    entry_id = e.get("id")
    category = e.get("category")
    timestamp = e.get("timestamp")
    if not (isinstance(entry_id, str) and entry_id):
        return None
    if category not in CATEGORIES:
        return None
    if not (isinstance(timestamp, str) and TS_RE.match(timestamp)):
        return None

    items = e.get("items")
    if not (isinstance(items, list) and all(isinstance(i, str) for i in items)):
        items = None
    locations = e.get("locations")
    if isinstance(locations, list):
        locations = [l for l in locations
                     if isinstance(l, dict)
                     and isinstance(l.get("item"), str)
                     and isinstance(l.get("location"), str)]
    else:
        locations = None

    amount = e.get("amount")
    amount = float(amount) if isinstance(amount, (int, float)) else None
    notes = e.get("notes") if isinstance(e.get("notes"), str) else None
    schedule_id = e.get("scheduleId") if isinstance(e.get("scheduleId"), str) else None

    return {
        "id": entry_id,
        "category": category,
        "items": json.dumps(items) if items else None,
        "locations": json.dumps(locations) if locations else None,
        "amount": amount,
        "timestamp": timestamp[:16],
        "schedule_id": schedule_id,
        "notes": notes,
        "deleted": 1 if e.get("deleted") else 0,
    }


def _clean_sched(s):
    if not isinstance(s, dict):
        return None
    if not (isinstance(s.get("id"), str) and s["id"]):
        return None
    if not (isinstance(s.get("time"), str) and re.match(r"^\d{2}:\d{2}$", s["time"])):
        return None
    if s.get("category") not in CATEGORIES:
        return None
    return {
        "id": s["id"],
        "time": s["time"],
        "category": s["category"],
        "item": s.get("item") if isinstance(s.get("item"), str) else None,
        "grp": 1 if s.get("group") else 0,
        "note": s.get("note") if isinstance(s.get("note"), str) else None,
    }


def _entry_out(row):
    return {
        "id": row["id"],
        "category": row["category"],
        "items": json.loads(row["items"]) if row["items"] else [],
        "locations": json.loads(row["locations"]) if row["locations"] else None,
        "amount": row["amount"],
        "timestamp": row["timestamp"],
        "scheduleId": row["schedule_id"],
        "notes": row["notes"],
        "source": row["source"],
    }


def create_app(config: dict, state: dict) -> FastAPI:
    app = FastAPI(title="cht-agent", docs_url=None, redoc_url=None, openapi_url=None)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=ALLOWED_ORIGINS,
        allow_methods=["GET", "POST", "OPTIONS"],
        allow_headers=["X-CHT-Secret", "Content-Type"],
    )

    def require_secret(request: Request) -> None:
        got = request.headers.get("X-CHT-Secret", "")
        if not hmac.compare_digest(got, config["app_shared_secret"]):
            raise HTTPException(status_code=401, detail="bad secret")

    @app.get("/health")
    def health():
        now = time.time()
        heartbeats = {
            name: {"ageSeconds": round(now - beat, 1)}
            for name, beat in state["heartbeats"].items()
        }
        return {
            "ok": True,
            "startedAt": state["started_at"],
            "heartbeats": heartbeats,
        }

    @app.post("/sync")
    async def sync(request: Request):
        require_secret(request)
        try:
            body = await request.json()
        except Exception:
            raise HTTPException(status_code=400, detail="invalid JSON")

        entries = body.get("entries") or []
        schedule = body.get("schedule")
        now = datetime.now().strftime("%Y-%m-%dT%H:%M")
        inserted, touched_dates = [], set()

        conn = db.connect(config["db_path"])
        try:
            for e in entries:
                row = _clean_entry(e)
                if not row:
                    log.warning("sync: skipped invalid entry %r",
                                e.get("id") if isinstance(e, dict) else e)
                    continue
                exists = conn.execute("SELECT 1 FROM entries WHERE id=?",
                                      (row["id"],)).fetchone()
                if exists:
                    # The app is authoritative for its own entries: edits and
                    # un-checks must reach the ledger. source/created_at keep
                    # their original values.
                    conn.execute(
                        "UPDATE entries SET items=?, locations=?, amount=?, "
                        "timestamp=?, schedule_id=?, notes=?, deleted=? WHERE id=?",
                        (row["items"], row["locations"], row["amount"],
                         row["timestamp"], row["schedule_id"], row["notes"],
                         row["deleted"], row["id"]))
                else:
                    conn.execute(
                        "INSERT INTO entries (id, category, items, locations, "
                        "amount, timestamp, schedule_id, source, notes, "
                        "created_at, deleted) VALUES (?,?,?,?,?,?,?,'app',?,?,?)",
                        (row["id"], row["category"], row["items"],
                         row["locations"], row["amount"], row["timestamp"],
                         row["schedule_id"], row["notes"], now, row["deleted"]))
                    inserted.append(row["id"])
                touched_dates.add(row["timestamp"][:10])

            if isinstance(schedule, list) and schedule:
                kept_ids = []
                for s in schedule:
                    srow = _clean_sched(s)
                    if not srow:
                        continue
                    kept_ids.append(srow["id"])
                    conn.execute(
                        "INSERT INTO schedule (id, time, category, item, grp, "
                        "note, active, updated_at) VALUES (?,?,?,?,?,?,1,?) "
                        "ON CONFLICT(id) DO UPDATE SET time=excluded.time, "
                        "category=excluded.category, item=excluded.item, "
                        "grp=excluded.grp, note=excluded.note, active=1, "
                        "updated_at=excluded.updated_at",
                        (srow["id"], srow["time"], srow["category"],
                         srow["item"], srow["grp"], srow["note"], now))
                if kept_ids:
                    marks = ",".join("?" * len(kept_ids))
                    conn.execute(
                        f"UPDATE schedule SET active=0 WHERE id NOT IN ({marks})",
                        kept_ids)
            conn.commit()
        finally:
            conn.close()

        for date in sorted(touched_dates):
            try:
                render_md.render_day(config["db_path"], config["markdown_dir"], date)
            except Exception:
                log.exception("markdown render failed for %s", date)

        return {"ok": True, "inserted": inserted}

    @app.get("/log")
    def get_log(request: Request, days: int = 7):
        require_secret(request)
        days = max(1, min(days, 90))
        today = datetime.now().strftime("%Y-%m-%d")
        start = (datetime.now() - timedelta(days=days - 1)).strftime("%Y-%m-%d")

        conn = db.connect(config["db_path"])
        try:
            rows = conn.execute(
                "SELECT * FROM entries WHERE deleted=0 AND timestamp >= ? "
                "ORDER BY timestamp DESC, created_at DESC", (start,)).fetchall()
            weight = conn.execute(
                "SELECT amount, timestamp FROM entries WHERE deleted=0 AND "
                "category='weight' AND amount IS NOT NULL "
                "ORDER BY timestamp DESC LIMIT 1").fetchone()
            patch_rows = conn.execute(
                "SELECT locations, timestamp FROM entries WHERE deleted=0 AND "
                "category='patches' AND locations IS NOT NULL "
                "ORDER BY timestamp DESC").fetchall()
        finally:
            conn.close()

        water_by_day = {}
        water_today_count = 0
        for r in rows:
            if r["category"] != "water":
                continue
            day = r["timestamp"][:10]
            if day == today:
                water_today_count += 1
            if r["amount"]:
                water_by_day[day] = water_by_day.get(day, 0) + r["amount"]

        # Most recent location per patch, across all time in the window.
        placements = {}
        for r in patch_rows:
            for loc in json.loads(r["locations"]):
                item = loc.get("item")
                if item and item not in placements:
                    placements[item] = {"item": item,
                                        "location": loc.get("location"),
                                        "timestamp": r["timestamp"]}

        return {
            "ok": True,
            "entries": [_entry_out(r) for r in rows],
            "totals": {
                "waterTodayOz": water_by_day.get(today, 0),
                "waterTodayCount": water_today_count,
                "waterByDay": water_by_day,
                "lastWeight": ({"amount": weight["amount"],
                                "timestamp": weight["timestamp"]}
                               if weight else None),
                "patchPlacements": sorted(placements.values(),
                                          key=lambda p: p["item"]),
            },
            "generatedAt": datetime.now().strftime("%Y-%m-%dT%H:%M"),
        }

    return app
