"""Claude tool-use agent for Christina's Telegram chat.

One call per incoming message: load the last ~20 turns from the
conversations table, run a claude-haiku-4-5 tool-use loop against the
health ledger, store both turns, return the reply text.

Every write re-renders that day's markdown. Item names mirror the app's
CATALOG (app.js) exactly so agent- and app-logged entries aggregate.
"""

import json
import logging
import re
import secrets
from datetime import datetime, timedelta

import anthropic

import db
import render_md

log = logging.getLogger("cht.agent")

MODEL = "claude-haiku-4-5"
MAX_TOOL_ROUNDS = 8
HISTORY_TURNS = 20
TS_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}$")

# A reply that claims a ledger action happened. Checked against turns where
# no tool ran at all — the model has repeatedly said "logged!" without
# calling log_entry (silently losing Christina's data), and the text-only
# conversation history teaches it to keep doing so once it starts.
ACTION_CLAIM_RE = re.compile(
    r"\b(logged|logging|updated|deleted|saved|recorded|done)\b", re.I)

GUARD_PROMPT = (
    "(automatic system check — this is not from Christina: your last reply "
    "claims something was logged/updated/deleted, but you called NO tools "
    "this turn, so nothing was actually saved. Use get_log to see what is "
    "really in the ledger, call log_entry for anything Christina reported "
    "that is missing, then send her one short corrected confirmation.)"
)

CATEGORIES = ("water", "supplements", "patches", "oils", "lotion", "weight")

# Mirrored from the app's CATALOG — patch names especially must match exactly.
APP_ITEMS = {
    "water": ["Light water", "Alkaline water", "Bottled water", "Other water"],
    "supplements": ["Cellergize (LifeWave)", "Transfer Factor Plus",
                    "ImmuneAdapt (A Fu Zheng)", "Bupleurum / Liver cleanse",
                    "Vitamin C", "Essiac tea (organic)", "Carcinosin 200c",
                    "Colostrum + Probiotic"],
    "patches": ["X39", "X49", "Aeon", "Energy", "Alavida", "Glutathione",
                "Carnosine", "Nirvana", "IceWave", "SP6 Complete"],
    "oils": ["Past Tense", "Immortelle", "Frankincense", "Birch", "Balance",
             "Rose", "Deep Blue (oil)", "Deep Blue (lotion)", "Cleansing",
             "On Guard", "Valor", "Three Wise Men", "Citrus blend", "Tea tree",
             "Lemon", "Peppermint", "Three in one", "Breathe",
             "Vitamin E oil (scar)"],
    "lotion": ["Magnesium lotion"],
}

PATCH_SPOTS = ("back of neck, base of skull (GB20), behind the ear, wrists, "
               "ankles, sole of the foot, over the liver, belly button, "
               "upper spine, lower back, shoulders")

TOOLS = [
    {
        "name": "log_entry",
        "description": "Log something Christina did: water, supplements, "
                       "patches, oils, lotion, or weight. Amount is ounces "
                       "for water and pounds for weight. For patches, include "
                       "locations (which patch went where).",
        "input_schema": {
            "type": "object",
            "properties": {
                "category": {"type": "string", "enum": list(CATEGORIES)},
                "items": {"type": "array", "items": {"type": "string"},
                          "description": "Item names, matching the known lists exactly when possible"},
                "amount": {"type": "number",
                           "description": "oz for water, lb for weight; omit otherwise"},
                "locations": {"type": "array", "items": {
                    "type": "object",
                    "properties": {"item": {"type": "string"},
                                   "location": {"type": "string"}},
                    "required": ["item", "location"]}},
                "timestamp": {"type": "string",
                              "description": "YYYY-MM-DDTHH:MM local time; omit to use right now"},
                "notes": {"type": "string"},
            },
            "required": ["category"],
        },
    },
    {
        "name": "get_log",
        "description": "Read recent entries from the ledger (newest first), "
                       "including their ids for update/delete.",
        "input_schema": {
            "type": "object",
            "properties": {
                "days": {"type": "integer", "description": "How many days back (default 2, max 30)"},
                "category": {"type": "string", "enum": list(CATEGORIES)},
            },
        },
    },
    {
        "name": "get_totals",
        "description": "Computed totals for a day: water ounces and count, "
                       "per-category counts, most recent weight.",
        "input_schema": {
            "type": "object",
            "properties": {
                "date": {"type": "string", "description": "YYYY-MM-DD; omit for today"},
            },
        },
    },
    {
        "name": "update_entry",
        "description": "Change fields on an existing entry (find its id with "
                       "get_log first). Only when Christina explicitly asks.",
        "input_schema": {
            "type": "object",
            "properties": {
                "id": {"type": "string"},
                "items": {"type": "array", "items": {"type": "string"}},
                "amount": {"type": "number"},
                "timestamp": {"type": "string"},
                "locations": {"type": "array", "items": {
                    "type": "object",
                    "properties": {"item": {"type": "string"},
                                   "location": {"type": "string"}},
                    "required": ["item", "location"]}},
                "notes": {"type": "string"},
            },
            "required": ["id"],
        },
    },
    {
        "name": "delete_entry",
        "description": "Soft-delete an entry (find its id with get_log first). "
                       "Only when Christina explicitly asks.",
        "input_schema": {
            "type": "object",
            "properties": {"id": {"type": "string"}},
            "required": ["id"],
        },
    },
    {
        "name": "get_schedule",
        "description": "Christina's daily schedule with a doneToday flag per row.",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "remember",
        "description": "Save a lasting fact about Christina to her profile "
                       "(usual glass size, preferred patch spots, routines...). "
                       "Not for individual log entries.",
        "input_schema": {
            "type": "object",
            "properties": {"note": {"type": "string"}},
            "required": ["note"],
        },
    },
]


def _now():
    return datetime.now().strftime("%Y-%m-%dT%H:%M")


def _ts_error(ts: str) -> str | None:
    """Validate a tool-supplied timestamp; returns an error string or None.

    Rejects the future: the model has stamped entries with tomorrow's date
    when backfilling "this morning", which corrupts day totals and schedule
    matching. 10-minute grace covers clock skew and "just now" rounding.
    """
    if not TS_RE.match(ts):
        return "timestamp must be YYYY-MM-DDTHH:MM"
    try:
        ts_dt = datetime.strptime(ts, "%Y-%m-%dT%H:%M")
    except ValueError:
        return "timestamp must be a real YYYY-MM-DDTHH:MM time"
    if ts_dt > datetime.now() + timedelta(minutes=10):
        return (f"timestamp {ts} is in the future — right now it is {_now()}; "
                "anything from earlier today gets today's date")
    return None


def _water_total(conn, date):
    row = conn.execute(
        "SELECT COALESCE(SUM(amount),0) FROM entries WHERE deleted=0 AND "
        "category='water' AND amount IS NOT NULL AND timestamp LIKE ?",
        (date + "T%",)).fetchone()
    return row[0]


def _render(config, date):
    try:
        render_md.render_day(config["db_path"], config["markdown_dir"], date)
    except Exception:
        log.exception("markdown render failed for %s", date)


def _entry_out(row):
    return {
        "id": row["id"],
        "category": row["category"],
        "items": json.loads(row["items"]) if row["items"] else [],
        "locations": json.loads(row["locations"]) if row["locations"] else None,
        "amount": row["amount"],
        "timestamp": row["timestamp"],
        "notes": row["notes"],
        "source": row["source"],
    }


# ---------- tool implementations ----------

def _t_log_entry(config, a):
    cat = a.get("category")
    if cat not in CATEGORIES:
        return {"error": f"unknown category {cat!r}"}
    ts = (a.get("timestamp") or _now())[:16]
    err = _ts_error(ts)
    if err:
        return {"error": err}
    items = a.get("items") or []
    locations = a.get("locations") or None
    amount = a.get("amount")
    entry_id = "tg-" + secrets.token_hex(5)

    conn = db.connect(config["db_path"])
    try:
        conn.execute(
            "INSERT INTO entries (id, category, items, locations, amount, "
            "timestamp, schedule_id, source, notes, created_at, deleted) "
            "VALUES (?,?,?,?,?,?,NULL,'telegram',?,?,0)",
            (entry_id, cat,
             json.dumps(items) if items else None,
             json.dumps(locations) if locations else None,
             float(amount) if amount is not None else None,
             ts, a.get("notes"), _now()))
        conn.commit()
        result = {"ok": True, "id": entry_id, "timestamp": ts}
        if cat == "water":
            result["waterTodayOz"] = _water_total(conn, ts[:10])
    finally:
        conn.close()
    _render(config, ts[:10])
    return result


def _t_get_log(config, a):
    days = max(1, min(int(a.get("days") or 2), 30))
    start = (datetime.now() - timedelta(days=days - 1)).strftime("%Y-%m-%d")
    q = ("SELECT * FROM entries WHERE deleted=0 AND timestamp >= ?"
         + (" AND category=?" if a.get("category") else "")
         + " ORDER BY timestamp DESC LIMIT 100")
    params = [start] + ([a["category"]] if a.get("category") else [])
    conn = db.connect(config["db_path"])
    try:
        rows = conn.execute(q, params).fetchall()
    finally:
        conn.close()
    return {"entries": [_entry_out(r) for r in rows]}


def _t_get_totals(config, a):
    date = a.get("date") or datetime.now().strftime("%Y-%m-%d")
    conn = db.connect(config["db_path"])
    try:
        counts = {c: n for c, n in conn.execute(
            "SELECT category, COUNT(*) FROM entries WHERE deleted=0 AND "
            "timestamp LIKE ? GROUP BY category", (date + "T%",))}
        water_oz = _water_total(conn, date)
        weight = conn.execute(
            "SELECT amount, timestamp FROM entries WHERE deleted=0 AND "
            "category='weight' AND amount IS NOT NULL "
            "ORDER BY timestamp DESC LIMIT 1").fetchone()
    finally:
        conn.close()
    return {
        "date": date,
        "waterOz": water_oz,
        "waterCount": counts.get("water", 0),
        "countsByCategory": counts,
        "lastWeight": ({"amount": weight["amount"], "timestamp": weight["timestamp"]}
                       if weight else None),
    }


def _t_update_entry(config, a):
    entry_id = a.get("id")
    conn = db.connect(config["db_path"])
    try:
        old = conn.execute("SELECT * FROM entries WHERE id=?", (entry_id,)).fetchone()
        if not old:
            return {"error": f"no entry with id {entry_id!r}"}
        sets, params = [], []
        if "items" in a and a["items"] is not None:
            sets.append("items=?"); params.append(json.dumps(a["items"]))
        if "locations" in a and a["locations"] is not None:
            sets.append("locations=?"); params.append(json.dumps(a["locations"]))
        if "amount" in a and a["amount"] is not None:
            sets.append("amount=?"); params.append(float(a["amount"]))
        if "timestamp" in a and a["timestamp"]:
            ts = a["timestamp"][:16]
            err = _ts_error(ts)
            if err:
                return {"error": err}
            sets.append("timestamp=?"); params.append(ts)
        if "notes" in a and a["notes"] is not None:
            sets.append("notes=?"); params.append(a["notes"])
        if not sets:
            return {"error": "nothing to change"}
        params.append(entry_id)
        conn.execute(f"UPDATE entries SET {', '.join(sets)} WHERE id=?", params)
        conn.commit()
        new = conn.execute("SELECT * FROM entries WHERE id=?", (entry_id,)).fetchone()
    finally:
        conn.close()
    _render(config, old["timestamp"][:10])
    if new["timestamp"][:10] != old["timestamp"][:10]:
        _render(config, new["timestamp"][:10])
    return {"ok": True, "entry": _entry_out(new)}


def _t_delete_entry(config, a):
    entry_id = a.get("id")
    conn = db.connect(config["db_path"])
    try:
        row = conn.execute("SELECT * FROM entries WHERE id=?", (entry_id,)).fetchone()
        if not row:
            return {"error": f"no entry with id {entry_id!r}"}
        conn.execute("UPDATE entries SET deleted=1 WHERE id=?", (entry_id,))
        conn.commit()
    finally:
        conn.close()
    _render(config, row["timestamp"][:10])
    return {"ok": True, "deleted": entry_id}


def _t_get_schedule(config, a):
    today = datetime.now().strftime("%Y-%m-%d")
    conn = db.connect(config["db_path"])
    try:
        sched = conn.execute(
            "SELECT * FROM schedule WHERE active=1 ORDER BY time").fetchall()
        todays = conn.execute(
            "SELECT schedule_id, category, items FROM entries WHERE deleted=0 "
            "AND timestamp LIKE ?", (today + "T%",)).fetchall()
    finally:
        conn.close()
    out = []
    for s in sched:
        out.append({"id": s["id"], "time": s["time"], "category": s["category"],
                    "item": s["item"], "group": bool(s["grp"]),
                    "note": s["note"],
                    "doneToday": db.schedule_row_done(s, todays)})
    return {"schedule": out}


def _t_remember(config, a):
    note = (a.get("note") or "").strip()
    if not note:
        return {"error": "empty note"}
    stamp = datetime.now().strftime("%Y-%m-%d")
    lead = ""
    try:
        with open(config["profile_path"], "rb") as f:
            data = f.read()
        if data and not data.endswith(b"\n"):
            lead = "\n"
    except OSError:
        pass
    with open(config["profile_path"], "a", encoding="utf-8") as f:
        f.write(f"{lead}- ({stamp}) {note}\n")
    return {"ok": True}


TOOL_FNS = {
    "log_entry": _t_log_entry,
    "get_log": _t_get_log,
    "get_totals": _t_get_totals,
    "update_entry": _t_update_entry,
    "delete_entry": _t_delete_entry,
    "get_schedule": _t_get_schedule,
    "remember": _t_remember,
}


def _run_tool(config, name, args):
    fn = TOOL_FNS.get(name)
    if not fn:
        return {"error": f"unknown tool {name!r}"}
    try:
        return fn(config, args or {})
    except Exception as exc:
        log.exception("tool %s failed", name)
        return {"error": f"{type(exc).__name__}: {exc}"}


# ---------- conversation memory ----------

def _load_history(config, chat_id):
    conn = db.connect(config["db_path"])
    try:
        rows = conn.execute(
            "SELECT role, content FROM conversations WHERE chat_id=? "
            "ORDER BY id DESC LIMIT ?",
            (str(chat_id), HISTORY_TURNS * 2)).fetchall()
    finally:
        conn.close()
    return [{"role": r["role"], "content": r["content"]} for r in reversed(rows)]


def _store_turn(config, chat_id, role, content):
    conn = db.connect(config["db_path"])
    try:
        conn.execute(
            "INSERT INTO conversations (chat_id, role, content, ts) VALUES (?,?,?,?)",
            (str(chat_id), role, content, _now()))
        conn.commit()
    finally:
        conn.close()


def _merge_alternating(msgs):
    """The API needs strictly alternating roles starting with 'user'."""
    out = []
    for m in msgs:
        if (out and out[-1]["role"] == m["role"]
                and isinstance(out[-1]["content"], str)
                and isinstance(m["content"], str)):
            out[-1]["content"] += "\n" + m["content"]
        else:
            out.append(dict(m))
    while out and out[0]["role"] != "user":
        out.pop(0)
    return out


# ---------- the agent ----------

def _system_prompt(config):
    now = datetime.now()
    # %-d / %#d are platform-specific; build the friendly date by hand
    when = (f"{now.strftime('%A, %B')} {now.day}, {now.year} at "
            f"{now.strftime('%I:%M %p').lstrip('0')}")
    try:
        with open(config["profile_path"], encoding="utf-8") as f:
            profile = f.read().strip()
    except OSError:
        profile = "(no profile yet)"
    items_desc = "\n".join(f"  {cat}: {', '.join(names)}"
                           for cat, names in APP_ITEMS.items())
    return f"""You are Christina's personal health-tracking assistant on Telegram. \
She texts (or voice-memos) what she did and you keep her ledger.

Right now it is {when} in Brighton, Colorado (America/Denver). \
Today's date is {now.strftime('%Y-%m-%d')}. All timestamps are local naive \
YYYY-MM-DDTHH:MM. Never use a future date: when she backfills something from \
earlier today, the date is {now.strftime('%Y-%m-%d')}.

Everything you log with log_entry lands in the same ledger her phone app \
reads — the app's Log tab shows your entries next time she opens it. There \
is no separate sync step and nothing Brian has to do. (Only the Today \
screen's checkmarks are phone-local; those she taps herself.)

What you know about Christina:
{profile}

Known item names (use these EXACT strings when logging so her app and your \
entries add up together; if she names something new, log her wording as-is):
{items_desc}
Weight is logged with amount in pounds and no items.

Common patch spots: {PATCH_SPOTS}.

Rules:
- CRITICAL: an entry exists ONLY if you called log_entry this turn and its \
result came back ok. NEVER tell her something is "logged" unless that \
happened in this very turn — saying "logged!" without the tool call loses \
her data. If you're unsure whether something was logged, check with get_log.
- Log what she tells you with log_entry. Water amounts are ounces — if she \
gives a container ("a bottle") without ounces, ask or use what you know about her.
- When she logs patches, record where each one went (locations). If she \
doesn't say where, ask — placement matters to her.
- Answer "did I / how much / when" questions with the tools (get_totals, \
get_log, get_schedule) — never from memory, never guess.
- Confirm each log in ONE short, warm sentence. When logging water, include \
today's running total (the tool returns it).
- Never update or delete an entry unless she explicitly asks.
- Use remember for lasting facts (her usual glass is 16 oz, favorite spots...), \
not for daily events.
- Keep replies short and friendly — she's on her phone. No markdown, no lists \
unless she asks. An emoji now and then is fine."""


def _tool_loop(client, config, system, messages, tools_used):
    """Run tool rounds until the model stops; returns the final reply text."""
    response = None
    for _ in range(MAX_TOOL_ROUNDS):
        response = client.messages.create(
            model=MODEL, max_tokens=1024, system=system,
            tools=TOOLS, messages=messages)
        if response.stop_reason != "tool_use":
            break
        messages.append({"role": "assistant", "content": response.content})
        results = []
        for block in response.content:
            if block.type == "tool_use":
                log.info("tool %s %s", block.name, json.dumps(block.input)[:200])
                out = _run_tool(config, block.name, block.input)
                tools_used.append(block.name)
                results.append({"type": "tool_result", "tool_use_id": block.id,
                                "content": json.dumps(out)})
        messages.append({"role": "user", "content": results})

    reply = "".join(b.text for b in response.content if b.type == "text").strip()
    return reply or "Done! 💛"


def handle_message(config, chat_id, text):
    """Run one user message through the agent; returns the reply text."""
    client = anthropic.Anthropic(api_key=config["anthropic_api_key"])
    history = _load_history(config, chat_id)
    _store_turn(config, chat_id, "user", text)
    messages = _merge_alternating(history + [{"role": "user", "content": text}])
    system = _system_prompt(config)

    tools_used = []
    reply = _tool_loop(client, config, system, messages, tools_used)

    # Grounding guard: a reply that claims a ledger action in a turn where
    # NO tool ran is a hallucinated confirmation (this silently lost entries
    # on 2026-07-08/09). One corrective round: verify with get_log, log what
    # is missing, restate.
    if not tools_used and ACTION_CLAIM_RE.search(reply):
        log.warning("guard: reply claims action but no tool ran — "
                    "forcing a verification round (%r)", reply[:120])
        messages.append({"role": "assistant", "content": reply})
        messages.append({"role": "user", "content": GUARD_PROMPT})
        reply = _tool_loop(client, config, system, messages, tools_used)

    _store_turn(config, chat_id, "assistant", reply)
    return reply
