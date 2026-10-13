"""Request id, body size limit, security headers and a one-line access log (pure ASGI)."""

from __future__ import annotations

import logging
import re
import secrets
import time
from typing import Any

from starlette.datastructures import Headers, MutableHeaders
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.core import errors
from app.core.logging import request_id_var

logger = logging.getLogger("studyroute.access")
_REQUEST_ID = re.compile(r"^[A-Za-z0-9_-]{6,64}$")

API_CSP = "default-src 'none'; frame-ancestors 'none'; base-uri 'none'; form-action 'none'"
DOCS_CSP = (
    "default-src 'self'; script-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; "
    "style-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; img-src 'self' data: "
    "https://fastapi.tiangolo.com; frame-ancestors 'none'"
)
DOCS_PATHS = ("/api/v1/docs", "/api/v1/redoc")

SECURITY_HEADERS = {
    "Strict-Transport-Security": "max-age=63072000; includeSubDomains",
    "X-Content-Type-Options": "nosniff",
    "Referrer-Policy": "no-referrer",
    "X-Frame-Options": "DENY",
    "Permissions-Policy": "camera=(), microphone=(), geolocation=()",
    "Cross-Origin-Opener-Policy": "same-origin",
}


class SecurityMiddleware:
    def __init__(self, app: ASGIApp, *, max_body_bytes: int) -> None:
        self.app = app
        self._max = max_body_bytes

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        headers = Headers(scope=scope)
        supplied = headers.get("x-request-id", "")
        request_id = supplied if _REQUEST_ID.match(supplied) else f"req_{secrets.token_hex(4)}"
        token = request_id_var.set(request_id)
        scope.setdefault("state", {})["request_id"] = request_id
        path = scope.get("path", "")
        status_code = 500
        started = time.perf_counter()

        async def send_wrapper(message: Message) -> None:
            nonlocal status_code
            if message["type"] == "http.response.start":
                status_code = message["status"]
                out = MutableHeaders(scope=message)
                out["X-Request-Id"] = request_id
                for name, value in SECURITY_HEADERS.items():
                    out[name] = value
                out["Content-Security-Policy"] = DOCS_CSP if path in DOCS_PATHS else API_CSP
                if path not in DOCS_PATHS:
                    out["Cache-Control"] = "no-store"
            await send(message)

        received = 0

        async def limited_receive() -> Message:
            nonlocal received
            message = await receive()
            if message["type"] == "http.request":
                received += len(message.get("body", b""))
                if received > self._max:
                    raise errors.PayloadTooLarge("The request body is too large.")
            return message

        try:
            declared = headers.get("content-length", "")
            if declared.isdigit() and int(declared) > self._max:
                too_big = errors.PayloadTooLarge("The request body is too large.")
                await errors.problem_response(too_big, request_id)(scope, receive, send_wrapper)
            else:
                await self.app(scope, limited_receive, send_wrapper)
        finally:
            ms = int((time.perf_counter() - started) * 1000)
            logger.info("%s %s -> %s (%d ms)", scope.get("method", "-"), path, status_code, ms)
            request_id_var.reset(token)


def cors_kwargs(origins: list[str]) -> dict[str, Any]:
    """Exact origins only, no wildcard, no credentials (we use bearer tokens, not cookies)."""
    return {
        "allow_origins": origins,
        "allow_credentials": False,
        "allow_methods": ["GET", "POST", "PATCH", "PUT", "DELETE", "OPTIONS"],
        "allow_headers": [
            "Authorization",
            "Content-Type",
            "Idempotency-Key",
            "X-MFA-Proof",
            "X-Request-Id",
        ],
        "expose_headers": ["X-Request-Id", "Idempotent-Replay", "Retry-After"],
        "max_age": 600,
    }
