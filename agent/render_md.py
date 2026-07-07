"""Deterministically render a daily markdown note from the SQLite ledger.

Called after every write (sync insert, agent log, edit, delete) so
D:\\Christina\\health-log\\YYYY-MM-DD.md always mirrors the database.
Pure code, no AI text — totals are computed, never generated.
"""

import json
import os
from datetime import datetime

import db

CATEGORY_LABELS = {
    "water": "Water",
    "supplements": "Supplements",
    "patches": "Patches",
    "oils": "Oils",
    "lotion": "Lotion",
    "weight": "Weight",
}


def _parse_json(text, default):
    if not text:
        return default
    try:
        return json.loads(text)
    except (ValueError, TypeError):
        return default


def _time_of(ts: str) -> str:
    # "2026-07-07T06:30" -> "06:30"
    return ts[11:16] if len(ts) >= 16 else ts


def _describe(row) -> str:
    category = row["category"]
    items = _parse_json(row["items"], [])
    locations = _parse_json(row["locations"], [])
    amount = row["amount"]
    parts = []

    if category == "water":
        oz = f"{amount:g} oz" if amount is not None else "water"
        label = ", ".join(items) if items else None
        parts.append(f"{oz} ({label})" if label else oz)
    elif category == "weight":
        parts.append(f"{amount:g} lb" if amount is not None else "weight")
    elif category == "patches":
        loc_by_item = {loc.get("item"): loc.get("location") for loc in locations
                       if isinstance(loc, dict)}
        if items:
            parts.append("; ".join(
                f"{item} @ {loc_by_item[item]}" if loc_by_item.get(item) else item
                for item in items))
        else:
            parts.append("patches")
    else:
        parts.append(", ".join(items) if items else CATEGORY_LABELS[category].lower())

    if row["notes"]:
        parts.append(f"— {row['notes']}")
    return " ".join(parts)


def render_day(db_path: str, markdown_dir: str, date: str) -> str:
    """Render one day's note ("YYYY-MM-DD"); returns the file path written."""
    conn = db.connect(db_path)
    try:
        rows = conn.execute(
            "SELECT * FROM entries WHERE deleted=0 AND timestamp LIKE ? "
            "ORDER BY timestamp, created_at",
            (date + "T%",)).fetchall()
    finally:
        conn.close()

    water_total = sum(r["amount"] or 0 for r in rows if r["category"] == "water")
    weights = [r["amount"] for r in rows if r["category"] == "weight" and r["amount"] is not None]

    day_name = datetime.strptime(date, "%Y-%m-%d").strftime("%A")
    lines = [f"# Health Log — {date} ({day_name})", ""]

    summary = [f"**Water:** {water_total:g} oz"]
    if weights:
        summary.append(f"**Weight:** {weights[-1]:g} lb")
    lines += [" · ".join(summary), ""]

    lines.append("## Timeline")
    if rows:
        running_water = 0.0
        for r in rows:
            desc = _describe(r)
            if r["category"] == "water" and r["amount"]:
                running_water += r["amount"]
                desc += f" (total {running_water:g} oz)"
            tag = " *(via chat)*" if r["source"] == "telegram" else ""
            lines.append(f"- **{_time_of(r['timestamp'])}** "
                         f"{CATEGORY_LABELS[r['category']].lower()} — {desc}{tag}")
    else:
        lines.append("- nothing logged yet")

    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    lines += ["", f"*Rendered from health-log.db at {now}.*", ""]

    os.makedirs(markdown_dir, exist_ok=True)
    path = os.path.join(markdown_dir, f"{date}.md")
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    return path


def render_today(db_path: str, markdown_dir: str) -> str:
    return render_day(db_path, markdown_dir, datetime.now().strftime("%Y-%m-%d"))
