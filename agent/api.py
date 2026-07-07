"""HTTP API for the tracker PWA, served on 127.0.0.1:8765 behind
`tailscale serve --https=8446` (tailnet-only, never public).

Phase 0: /health. Phase 1 adds /sync and /log.
"""

import time

from fastapi import FastAPI


def create_app(config: dict, state: dict) -> FastAPI:
    app = FastAPI(title="cht-agent", docs_url=None, redoc_url=None, openapi_url=None)

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

    return app
