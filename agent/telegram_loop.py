"""Telegram long-polling chat loop.

Outbound-only: getUpdates long-poll reaches out to Telegram's cloud, nothing
reaches in. Network blips must never kill the loop — every iteration is
wrapped in a catch-all with backoff.

Phase 0 behavior: log every incoming chat id (so Brian can copy new ids into
the allowlist), politely turn away non-allowlisted chats, and tell allowlisted
chats the agent brain is still being wired up. Phase 2 replaces the allowlisted
branch with the Claude tool-use agent (agent_llm.handle_message).
"""

import logging
import time

import requests

log = logging.getLogger("cht.telegram")

POLL_TIMEOUT = 50
ERROR_BACKOFF_SECONDS = 10


def _beat(state):
    state["heartbeats"]["telegram"] = time.time()


def send_message(token: str, chat_id, text: str) -> None:
    resp = requests.post(
        f"https://api.telegram.org/bot{token}/sendMessage",
        json={"chat_id": chat_id, "text": text},
        timeout=15,
    )
    resp.raise_for_status()


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

    log.info("message from allowed chat %s (%s)", chat_id, who)
    # Phase 2: hand off to agent_llm.handle_message here.
    send_message(token, chat_id,
                 "Hi! I'm Christina's health tracker bot. My brain is still "
                 "being set up — check back soon.")


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
