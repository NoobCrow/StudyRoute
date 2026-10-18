"""One managed Python process: FastAPI and a committed Next static export, same origin."""

from __future__ import annotations

import json
import os
import re
from pathlib import Path
from urllib.parse import urlsplit

from fastapi import FastAPI
from starlette.datastructures import MutableHeaders
from starlette.exceptions import HTTPException
from starlette.staticfiles import StaticFiles
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.core.config import get_settings
from app.main import create_app as create_api

ROOT = Path(__file__).resolve().parents[2]
HASH = re.compile(r"^'sha256-[A-Za-z0-9+/]{43}='$")


def ui_policy(root: Path) -> str:
    manifest = json.loads((root / "csp-hashes.json").read_text(encoding="utf-8"))
    hashes = manifest.get("hashes")
    if (
        not isinstance(hashes, list)
        or not hashes
        or not all(isinstance(value, str) and HASH.fullmatch(value) for value in hashes)
    ):
        raise RuntimeError("Invalid CSP manifest. Rebuild the Botkeep frontend.")
    return (
        "default-src 'self'; script-src 'self' "
        + " ".join(hashes)
        + "; style-src 'self'; img-src 'self' data:; font-src 'self'; connect-src 'self'; "
        "frame-ancestors 'none'; base-uri 'none'; form-action 'self'; object-src 'none'"
    )


class Frontend(StaticFiles):
    async def get_response(self, path: str, scope: Scope):
        parts = Path(path).parts
        if parts and (parts[0] in {"api", "health"} or any(p.startswith(".") for p in parts)):
            raise HTTPException(status_code=404)
        response = await super().get_response(path, scope)
        if response.status_code in {301, 302, 307, 308} and "location" in response.headers:
            target = urlsplit(response.headers["location"])
            response.headers["location"] = target.path + (
                "?" + target.query if target.query else ""
            )
        return response


class FrontendHeaders:
    def __init__(self, app: ASGIApp, *, policy: str) -> None:
        self.app = app
        self.policy = policy

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        path = scope.get("path", "")
        if scope["type"] != "http" or path == "/health" or path.startswith("/api/"):
            await self.app(scope, receive, send)
            return

        async def headers(message: Message) -> None:
            if message["type"] == "http.response.start":
                out = MutableHeaders(scope=message)
                out["Content-Security-Policy"] = self.policy
                out["Cache-Control"] = (
                    "public, max-age=31536000, immutable"
                    if path.startswith("/_next/static/") and message["status"] == 200
                    else "no-store"
                )
            await send(message)

        await self.app(scope, receive, headers)


def create_app() -> FastAPI:
    settings = get_settings()
    root = Path(
        os.environ.get("STUDYROUTE_STATIC_DIR") or str(ROOT / "deploy" / "botkeep" / "site")
    ).resolve()
    if not (root / "login" / "index.html").is_file():
        raise RuntimeError(
            "Botkeep frontend missing. Commit deploy/botkeep/site; "
            "run npm run build in web/, then python scripts/prepare_botkeep.py."
        )
    policy = ui_policy(root)
    app = create_api(settings)
    if settings.is_sandbox and os.environ.get("BOTKEEP_SEED_DEMO", "true").lower() == "true":
        from app.scripts.seed import seed_demo

        seed_demo(app.state.ctx)
    app.mount("/", Frontend(directory=root, html=True), name="frontend")
    app.add_middleware(FrontendHeaders, policy=policy)
    return app
