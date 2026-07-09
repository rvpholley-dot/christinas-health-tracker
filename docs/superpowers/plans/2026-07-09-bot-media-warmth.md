# Bot Media & Warmth Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** The Telegram bot sees photos (vision), saves every file Christina sends to a dated inbox folder, and never scope-polices off-topic messages.

**Architecture:** `telegram_loop.py` grows download/save helpers and a media branch in `_handle_update`; `agent_llm.handle_message` accepts base64 images and sends them as vision blocks (history keeps a text placeholder); the system prompt gains photo + warmth rules. Spec: `docs/superpowers/specs/2026-07-09-bot-media-warmth-design.md`.

**Tech Stack:** Python 3.13 (`C:\Python313\python.exe`), Telegram Bot API (`getFile` — 20 MB cap), Anthropic vision (claude-haiku-4-5).

**Repo:** `D:\Users\brian\Projects\Personal\christinas-health-tracker`. Agent-side only; no app/Pages deploy. Live agent restarts ~15 s after killing the `cht_agent.py` process.

---

### Task 1: make `_merge_alternating` safe for image-block turns

**Files:**
- Test (create): `agent/test_agent_llm.py`
- Modify: `agent/agent_llm.py` (`_merge_alternating`)

- [ ] **Step 1: Write the failing test**

Create `agent/test_agent_llm.py`:

```python
"""Tests for agent_llm pure helpers. Run:
C:\\Python313\\python.exe agent\\test_agent_llm.py"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import agent_llm

fails = 0


def check(name, cond):
    global fails
    print(("PASS" if cond else "FAIL") + "  " + name)
    if not cond:
        fails += 1


IMG_BLOCKS = [{"type": "image", "source": {"type": "base64",
              "media_type": "image/png", "data": "AAAA"}},
              {"type": "text", "text": "(photo saved) look!"}]

# consecutive user turns where the second is block content must NOT be
# string-concatenated (that raises TypeError today)
out = agent_llm._merge_alternating([
    {"role": "user", "content": "hi"},
    {"role": "assistant", "content": "hey"},
    {"role": "user", "content": "one"},
    {"role": "user", "content": IMG_BLOCKS},
])
check("block turn survives merge", out[-1]["content"] == IMG_BLOCKS)
check("string turns still merge", agent_llm._merge_alternating(
    [{"role": "user", "content": "a"}, {"role": "user", "content": "b"}]
)[0]["content"] == "a\nb")
check("leading non-user still dropped", agent_llm._merge_alternating(
    [{"role": "assistant", "content": "x"}, {"role": "user", "content": "y"}]
)[0]["role"] == "user")

print("\nFAILURES:", fails)
sys.exit(1 if fails else 0)
```

- [ ] **Step 2: Run it to verify it fails**

Run: `C:\Python313\python.exe agent\test_agent_llm.py`
Expected: TypeError (`can only concatenate str (not "list") to str`) or a
FAIL on the first check.

- [ ] **Step 3: Fix the merge condition**

In `agent_llm.py` `_merge_alternating`, require BOTH contents to be strings:

```python
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `C:\Python313\python.exe agent\test_agent_llm.py` → all PASS.

- [ ] **Step 5: Commit**

```bash
git add agent/agent_llm.py agent/test_agent_llm.py
git commit -m "fix(agent): _merge_alternating tolerates image-block content"
```

---

### Task 2: download & inbox-save helpers

**Files:**
- Test (create): `agent/test_telegram_media.py`
- Modify: `agent/telegram_loop.py` (new imports + two functions)

- [ ] **Step 1: Write the failing test**

Create `agent/test_telegram_media.py`:

```python
"""Tests for the inbox save helper. Run:
C:\\Python313\\python.exe agent\\test_telegram_media.py"""
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import telegram_loop

fails = 0


def check(name, cond):
    global fails
    print(("PASS" if cond else "FAIL") + "  " + name)
    if not cond:
        fails += 1


tmp = tempfile.mkdtemp()
config = {"inbox_dir": tmp}

p1 = telegram_loop.save_inbox_file(config, b"12345", ".jpg", "photo")
check("file written", open(p1, "rb").read() == b"12345")
check("dated subfolder + kind in name",
      os.sep.join(p1.split(os.sep)[-2:]).count("-") >= 3
      and "photo" in os.path.basename(p1) and p1.endswith(".jpg"))
p2 = telegram_loop.save_inbox_file(config, b"67890", ".jpg", "photo")
check("same-second collision gets a distinct name", p1 != p2)
p3 = telegram_loop.save_inbox_file(config, b"x", "", "document")
check("missing extension falls back to .bin", p3.endswith(".bin"))

print("\nFAILURES:", fails)
sys.exit(1 if fails else 0)
```

- [ ] **Step 2: Run it to verify it fails**

Run: `C:\Python313\python.exe agent\test_telegram_media.py`
Expected: AttributeError (`save_inbox_file` doesn't exist).

- [ ] **Step 3: Implement both helpers**

In `telegram_loop.py`, extend the imports:

```python
import base64
import logging
import os
import time
from datetime import datetime

import requests
```

Add below `transcribe_voice`:

```python
DEFAULT_INBOX = r"D:\Christina\cht-agent\inbox"
MAX_IMAGE_BYTES = 4_000_000      # keep well under the API's 5 MB image cap


def download_telegram_file(token: str, file_id: str) -> tuple[bytes, str]:
    """Fetch a file from Telegram; returns (bytes, extension incl. dot).
    Telegram's getFile refuses files over 20 MB — that surfaces as an
    HTTP error the caller handles."""
    r = requests.get(f"https://api.telegram.org/bot{token}/getFile",
                     params={"file_id": file_id}, timeout=30)
    r.raise_for_status()
    file_path = r.json()["result"]["file_path"]
    ext = os.path.splitext(file_path)[1]
    resp = requests.get(f"https://api.telegram.org/file/bot{token}/{file_path}",
                        timeout=120)
    resp.raise_for_status()
    return resp.content, ext


def save_inbox_file(config: dict, data: bytes, ext: str, kind: str) -> str:
    """Save bytes to <inbox_dir>\\YYYY-MM-DD\\HHMMSS-<kind><ext>; never
    overwrites (suffix on collision). Returns the full path."""
    day_dir = os.path.join(config.get("inbox_dir", DEFAULT_INBOX),
                           datetime.now().strftime("%Y-%m-%d"))
    os.makedirs(day_dir, exist_ok=True)
    base = f"{datetime.now().strftime('%H%M%S')}-{kind}"
    ext = ext or ".bin"
    path = os.path.join(day_dir, base + ext)
    n = 1
    while os.path.exists(path):
        path = os.path.join(day_dir, f"{base}-{n}{ext}")
        n += 1
    with open(path, "wb") as f:
        f.write(data)
    return path
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `C:\Python313\python.exe agent\test_telegram_media.py` → all PASS.

- [ ] **Step 5: Commit**

```bash
git add agent/telegram_loop.py agent/test_telegram_media.py
git commit -m "feat(agent): telegram file download + dated inbox save helpers"
```

---

### Task 3: media branch in `_handle_update`, vision in `handle_message`, warmth prompt

**Files:**
- Modify: `agent/telegram_loop.py` (`_handle_update`)
- Modify: `agent/agent_llm.py` (`handle_message`, `_system_prompt`)

- [ ] **Step 1: photos and other media in `_handle_update`**

In `telegram_loop.py`, replace the body from `text = message.get("text")`
down to (but not including) `log.info("message from %s ...` with:

```python
    text = message.get("text")
    images = None
    caption = (message.get("caption") or "").strip()

    if not text and message.get("photo"):
        send_typing(token, chat_id)
        try:
            sizes = [p for p in message["photo"]
                     if (p.get("file_size") or 0) <= MAX_IMAGE_BYTES]
            best = (sizes or message["photo"][:1])[-1]  # sizes run small→large
            data, ext = download_telegram_file(token, best["file_id"])
            path = save_inbox_file(config, data, ext or ".jpg", "photo")
            log.info("photo from %s (%s) saved to %s", who, chat_id, path)
            images = [{"media_type": "image/jpeg",
                       "data": base64.b64encode(data).decode()}]
            text = f"(she sent a photo — saved to {path})"
            if caption:
                text += f" {caption}"
        except Exception:
            log.exception("photo handling failed for chat %s", chat_id)
            send_message(token, chat_id,
                         "I had trouble opening that photo — mind sending it again? 💛")
            return

    if not text and not images:
        for kind in ("video", "video_note", "animation", "document", "audio", "sticker"):
            media = message.get(kind)
            if not media:
                continue
            send_typing(token, chat_id)
            try:
                data, ext = download_telegram_file(token, media["file_id"])
                path = save_inbox_file(config, data, ext, kind)
                log.info("%s from %s (%s) saved to %s", kind, who, chat_id, path)
                text = (f"(she sent a {kind} — you can't watch/open it, but it's "
                        f"saved at {path} for Brian; respond warmly)")
            except Exception:
                log.exception("%s handling failed for chat %s", kind, chat_id)
                text = (f"(she sent a {kind} that couldn't be saved — too big or "
                        "a network hiccup; respond warmly, don't be technical)")
            if caption:
                text += f" {caption}"
            break

    if not text and message.get("voice"):
        ...  # existing voice block, unchanged

    if not text:
        send_message(token, chat_id,
                     "I couldn't quite open that one — but send me texts, voice "
                     "memos, or photos anytime! 💛")
        return
```

(The existing voice block and everything after stay as they are, except the
final agent call — next step.)

- [ ] **Step 2: pass images through to the agent**

Still in `_handle_update`, the agent call becomes:

```python
    try:
        reply = agent_llm.handle_message(config, chat_id, text, images=images)
```

In `agent_llm.py`, change `handle_message`:

```python
def handle_message(config, chat_id, text, images=None):
    """Run one user message through the agent; returns the reply text.
    `images`: optional list of {"media_type", "data"(base64)} shown to the
    model this turn only — history stores just the text placeholder."""
    client = anthropic.Anthropic(api_key=config["anthropic_api_key"])
    history = _load_history(config, chat_id)
    _store_turn(config, chat_id, "user", text)
    if images:
        content = [{"type": "image",
                    "source": {"type": "base64",
                               "media_type": img["media_type"],
                               "data": img["data"]}}
                   for img in images]
        content.append({"type": "text", "text": text})
        user_msg = {"role": "user", "content": content}
    else:
        user_msg = {"role": "user", "content": text}
    messages = _merge_alternating(history + [user_msg])
    system = _system_prompt(config)
    ...  # tool loop + grounding guard, unchanged
```

- [ ] **Step 3: warmth + photo rules in the system prompt**

In `_system_prompt`, add two rules to the end of the `Rules:` block:

```python
- She may send photos, and you can SEE them. React to what's actually in \
the picture, warmly and specifically. If it clearly shows something \
loggable (patches on her skin, the scale, a supplement), offer to log it — \
or just log it when it's unambiguous. Every file she sends is saved for \
Brian automatically; you never need to explain that unless she asks.
- Anything outside health tracking — stories, feelings, photos of family, \
whatever she wants to share — gets a warm, brief, natural reply, like a \
friend would give. NEVER tell her something is outside your scope or "not \
your function." Use remember if it's a lasting personal fact.
```

- [ ] **Step 4: Run all agent tests**

```
C:\Python313\python.exe agent\test_agent_llm.py
C:\Python313\python.exe agent\test_telegram_media.py
C:\Python313\python.exe agent\test_api.py   (if Task exists from pull-sync plan)
```
All PASS. Also: `C:\Python313\python.exe -c "import sys; sys.path.insert(0,'agent'); import telegram_loop, agent_llm"` → no ImportError.

- [ ] **Step 5: Vision smoke test (sandbox — real API call, no Telegram)**

```python
# scratchpad script; uses a sandbox DB copy so nothing touches production
import base64, json, shutil, sys
sys.path.insert(0, r"D:\Users\brian\Projects\Personal\christinas-health-tracker\agent")
import agent_llm
SB = r"<scratchpad>"
shutil.copy(r"D:\Christina\health-log.db", SB + r"\vision-sandbox.db")
config = json.load(open(r"D:\Christina\cht-agent\config.json", encoding="utf-8"))
config["db_path"] = SB + r"\vision-sandbox.db"
config["markdown_dir"] = SB + r"\md"
PNG_1x1 = ("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR4"
           "2mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg==")
reply = agent_llm.handle_message(
    config, "visiontest", "(she sent a photo — saved to X) what do you see?",
    images=[{"media_type": "image/png", "data": PNG_1x1}])
print("REPLY:", reply)
```
Expected: a friendly reply (about a tiny/blank image) — proves the vision
block round-trips with tools attached, no exception.

- [ ] **Step 6: Commit**

```bash
git add agent/telegram_loop.py agent/agent_llm.py
git commit -m "feat(agent): bot sees photos, saves all media to inbox, warmth rules"
```

---

### Task 4: deploy + live check

- [ ] **Step 1: Restart the live agent** — kill the `cht_agent.py` python
process; launcher restarts in ~15 s. Verify `GET /health` shows fresh
`startedAt` and both heartbeats.

- [ ] **Step 2: Live test with Brian's own Telegram** (his chat id is
allowlisted): send the bot a photo with a caption. EXPECT: the file lands in
`D:\Christina\cht-agent\inbox\<today>\`, the reply mentions what's in the
photo, `agent.log` shows the save line, and the conversations table stores
the `(she sent a photo — saved to ...)` placeholder.

- [ ] **Step 3: Watch the next few real exchanges** in `agent.log` for the
grounding guard + media paths behaving (no `guard:` warnings storms, no
media exceptions).
