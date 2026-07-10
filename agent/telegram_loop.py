"""Telegram long-polling chat loop.

Outbound-only: getUpdates long-poll reaches out to Telegram's cloud, nothing
reaches in. Network blips must never kill the loop — every iteration is
wrapped in a catch-all with backoff.

Unknown chat ids are logged (so Brian can copy them into the allowlist) and
politely turned away. Allowlisted messages go to the Claude agent
(agent_llm.handle_message); voice memos are transcribed first via
ElevenLabs Speech-to-Text (scribe_v1 — Telegram's OGG/Opus is supported).
"""

import base64
import logging
import os
import time
from datetime import datetime

import requests

import agent_llm

log = logging.getLogger("cht.telegram")

POLL_TIMEOUT = 50
ERROR_BACKOFF_SECONDS = 10
DEFAULT_INBOX = r"D:\Christina\cht-agent\inbox"
MAX_IMAGE_BYTES = 4_000_000      # keep well under the API's 5 MB image cap


def _beat(state):
    state["heartbeats"]["telegram"] = time.time()


def send_message(token: str, chat_id, text: str) -> None:
    resp = requests.post(
        f"https://api.telegram.org/bot{token}/sendMessage",
        json={"chat_id": chat_id, "text": text},
        timeout=15,
    )
    resp.raise_for_status()


def send_typing(token: str, chat_id) -> None:
    try:
        requests.post(f"https://api.telegram.org/bot{token}/sendChatAction",
                      json={"chat_id": chat_id, "action": "typing"}, timeout=10)
    except Exception:
        pass  # cosmetic only


def transcribe_voice(config: dict, file_id: str) -> str:
    """Download a Telegram voice memo and transcribe it with ElevenLabs."""
    token = config["telegram_bot_token"]
    r = requests.get(f"https://api.telegram.org/bot{token}/getFile",
                     params={"file_id": file_id}, timeout=30)
    r.raise_for_status()
    file_path = r.json()["result"]["file_path"]
    audio = requests.get(f"https://api.telegram.org/file/bot{token}/{file_path}",
                         timeout=60)
    audio.raise_for_status()
    resp = requests.post(
        "https://api.elevenlabs.io/v1/speech-to-text",
        headers={"xi-api-key": config["elevenlabs_api_key"]},
        data={"model_id": "scribe_v1"},
        files={"file": ("voice.ogg", audio.content, "audio/ogg")},
        timeout=120,
    )
    resp.raise_for_status()
    return (resp.json().get("text") or "").strip()


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


def _handle_update(update: dict, config: dict) -> None:
    message = update.get("message")
    if not message:
        return
    chat = message.get("chat", {})
    chat_id = chat.get("id")
    who = chat.get("first_name") or chat.get("username") or "?"
    token = config["telegram_bot_token"]
    allowed = {str(c) for c in config.get("allowed_chat_ids", [])}

    if str(chat_id) not in allowed:
        log.info("unknown chat id %s (%s) — add to allowed_chat_ids to allow", chat_id, who)
        send_message(token, chat_id, "Sorry, this is a private bot.")
        return

    text = message.get("text")
    if not text and message.get("voice"):
        send_typing(token, chat_id)
        try:
            text = transcribe_voice(config, message["voice"]["file_id"])
            log.info("voice memo from %s (%s) transcribed: %r", who, chat_id, text[:120])
        except Exception:
            log.exception("voice transcription failed for chat %s", chat_id)
            send_message(token, chat_id,
                         "Sorry, I couldn't make that one out — try typing it?")
            return
    if not text:
        send_message(token, chat_id,
                     "I can read texts and voice memos — send me one of those. 💛")
        return

    log.info("message from %s (%s): %r", who, chat_id, text[:120])
    send_typing(token, chat_id)
    try:
        reply = agent_llm.handle_message(config, chat_id, text)
    except Exception:
        log.exception("agent failed for chat %s", chat_id)
        reply = "Oof, something glitched on my end. Try again in a minute?"
    send_message(token, chat_id, reply)


def run(config: dict, state: dict) -> None:
    token = config.get("telegram_bot_token")
    if not token:
        log.warning("telegram_bot_token not configured — chat loop idle")
        while True:
            _beat(state)
            time.sleep(30)

    log.info("telegram long-poll loop starting")
    offset = None
    while True:
        _beat(state)
        try:
            params = {"timeout": POLL_TIMEOUT}
            if offset is not None:
                params["offset"] = offset
            resp = requests.get(
                f"https://api.telegram.org/bot{token}/getUpdates",
                params=params,
                timeout=POLL_TIMEOUT + 10,
            )
            resp.raise_for_status()
            for update in resp.json().get("result", []):
                offset = update["update_id"] + 1
                try:
                    _handle_update(update, config)
                except Exception:
                    log.exception("failed handling update %s", update.get("update_id"))
        except Exception as exc:
            log.warning("telegram poll error (%s) — retrying in %ss", exc, ERROR_BACKOFF_SECONDS)
            time.sleep(ERROR_BACKOFF_SECONDS)
