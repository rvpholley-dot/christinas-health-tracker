"""cht-agent — Christina's health tracker agent service.

One process, three loops:
  · HTTP API for the PWA (FastAPI/uvicorn on 127.0.0.1:8765,
    reached over the tailnet via `tailscale serve --https=8446`)
  · Telegram long-poll chat loop (background thread)
  · Missed-dose reminder loop (background thread)

Config with secrets lives OUTSIDE this public repo at
D:\\Christina\\cht-agent\\config.json (override with env CHT_CONFIG).

Run:  C:\\Python313\\python.exe cht_agent.py
"""

import json
import logging
import os
import sys
import threading
from datetime import datetime
from logging.handlers import RotatingFileHandler

import uvicorn

import api
import create_db
import reminders
import telegram_loop

DEFAULT_CONFIG_PATH = r"D:\Christina\cht-agent\config.json"

log = logging.getLogger("cht")


def load_config() -> dict:
    path = os.environ.get("CHT_CONFIG", DEFAULT_CONFIG_PATH)
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def setup_logging(log_path: str) -> None:
    os.makedirs(os.path.dirname(log_path), exist_ok=True)
    fmt = logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s",
                            datefmt="%Y-%m-%d %H:%M:%S")
    file_handler = RotatingFileHandler(log_path, maxBytes=2_000_000, backupCount=5,
                                       encoding="utf-8")
    file_handler.setFormatter(fmt)
    stream_handler = logging.StreamHandler(sys.stderr)
    stream_handler.setFormatter(fmt)
    logging.basicConfig(level=logging.INFO, handlers=[file_handler, stream_handler])


def start_thread(name: str, target, config: dict, state: dict) -> None:
    thread = threading.Thread(target=target, args=(config, state),
                              name=name, daemon=True)
    thread.start()


def main() -> None:
    config = load_config()
    setup_logging(config.get("log_path", r"D:\Christina\cht-agent\agent.log"))
    log.info("cht-agent starting")

    create_db.ensure_db(config["db_path"])

    state = {
        "started_at": datetime.now().strftime("%Y-%m-%dT%H:%M:%S"),
        "heartbeats": {},
    }

    start_thread("telegram", telegram_loop.run, config, state)
    start_thread("reminders", reminders.run, config, state)

    app = api.create_app(config, state)
    uvicorn.run(app,
                host=config.get("http_host", "127.0.0.1"),
                port=config.get("http_port", 8765),
                log_config=None)


if __name__ == "__main__":
    main()
