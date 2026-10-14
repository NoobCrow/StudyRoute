"""scripts/docker_smoke.py: it passes a healthy stack and names what is wrong with a broken one."""

from __future__ import annotations

import importlib.util
import json
import re
import sys
import threading
from collections.abc import Iterator
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("docker_smoke", ROOT / "scripts" / "docker_smoke.py")
assert spec and spec.loader
smoke = importlib.util.module_from_spec(spec)
sys.modules["docker_smoke"] = smoke  # dataclasses look the module up here
spec.loader.exec_module(smoke)

INDEX = b'<!doctype html><div id="root"></div><script type="module" src="/assets/index-abc.js"></script>'


def repo_security_headers() -> dict[str, str]:
    """The exact headers frontend/security_headers.conf makes nginx send."""
    text = (ROOT / "frontend" / "security_headers.conf").read_text(encoding="utf-8")
    return dict(re.findall(r'add_header\s+(\S+)\s+"(.*)"\s+always;', text))


class Stack(BaseHTTPRequestHandler):
    """A stand-in for nginx plus the API. `broken` drops the CSP and the sandbox marker;
    `duplicated` sends the API's CSP twice, as nginx did before its /api/ block stopped adding it."""

    broken = False
    duplicated = False

    def version_string(self) -> str:  # the one Server header, without a version
        return "nginx"

    def _send(
        self,
        status: int,
        body: bytes,
        kind: str,
        extra: dict[str, str] | None = None,
        twice: bool = False,
    ) -> None:
        self.send_response(status)
        self.send_header("Content-Type", kind)
        for name, value in (extra or {}).items():
            for _ in range(2 if twice else 1):
                self.send_header(name, value)
        if not self.broken:
            self.send_header("X-Sandbox", "true")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _web_headers(self) -> dict[str, str]:
        headers = repo_security_headers()
        if self.broken:
            headers.pop("Content-Security-Policy", None)
        return headers

    def do_GET(self) -> None:
        path = self.path.split("?")[0]
        if path.startswith("/assets/"):
            headers = {**self._web_headers(), "Cache-Control": "public, immutable"}
            self._send(200, b"console.log(1)", "text/javascript", headers)
        elif path in ("/health", "/api/v1/health"):
            body = json.dumps({"status": "ok", "mode": "sandbox"}).encode()
            csp = {} if path == "/health" else {"Content-Security-Policy": "default-src 'none'"}
            self._send(200, body, "application/json", csp, twice=self.duplicated)
        elif path == "/api/v1/sandbox":
            scenarios = [{"token": t} for t in ("FAIL_TEST", "SLOW_TEST", "SANCTION_TEST")]
            self._send(200, json.dumps({"scenarios": scenarios}).encode(), "application/json")
        elif path == "/api/v1/me":
            self._send(
                401,
                b'{"code":"UNAUTHENTICATED"}',
                "application/problem+json",
                {"X-Request-Id": "req_1"},
            )
        elif path.startswith("/api/"):
            self._send(404, b"{}", "application/json")
        else:
            self._send(200, INDEX, "text/html", self._web_headers())

    def do_POST(self) -> None:
        declared = int(self.headers.get("Content-Length", "0"))
        if declared > 65_536:  # refused from the header alone, like nginx and the API do
            self._send(413, b'{"code":"PAYLOAD_TOO_LARGE"}', "application/problem+json")
        else:
            self.rfile.read(declared)
            self._send(400, b"{}", "application/json")

    def log_message(self, *args: object) -> None:  # silence the test output
        return


def serve(broken: bool, duplicated: bool = False) -> Iterator[str]:
    handler = type("Handler", (Stack,), {"broken": broken, "duplicated": duplicated})
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        yield f"http://127.0.0.1:{server.server_address[1]}"
    finally:
        server.shutdown()
        server.server_close()


@pytest.fixture
def healthy() -> Iterator[str]:
    yield from serve(broken=False)


@pytest.fixture
def broken() -> Iterator[str]:
    yield from serve(broken=True)


@pytest.fixture
def duplicating() -> Iterator[str]:
    yield from serve(broken=False, duplicated=True)


def test_a_healthy_stack_passes_every_check(
    healthy: str, capsys: pytest.CaptureFixture[str]
) -> None:
    assert smoke.main([healthy]) == 0
    out = capsys.readouterr().out
    assert "FAIL" not in out and "All smoke checks passed." in out
    assert out.count("OK  ") >= 20


def test_the_api_only_mode_skips_the_web_checks(
    healthy: str, capsys: pytest.CaptureFixture[str]
) -> None:
    assert smoke.main([healthy, "--api-only"]) == 0
    assert "The web server" not in capsys.readouterr().out


def test_a_stack_without_a_csp_and_the_sandbox_marker_fails_and_says_why(broken: str) -> None:
    report = smoke.Report()
    smoke.check_web(broken, report)
    joined = " | ".join(report.failures)
    assert "CSP: default-src 'self'" in joined
    assert "X-Sandbox" in joined
    assert "assets carry the security headers too" in joined
    assert smoke.main([broken]) == 1


def test_a_security_header_sent_twice_is_flagged(duplicating: str) -> None:
    report = smoke.Report()
    smoke.check_api(duplicating, report)
    assert report.failures == ["each API security header is sent once, not twice"]


def test_an_unreachable_stack_is_reported_not_crashed(capsys: pytest.CaptureFixture[str]) -> None:
    assert smoke.main(["http://127.0.0.1:9"]) == 2
    assert "docker compose up" in capsys.readouterr().err


def test_the_stand_in_really_uses_the_repos_security_headers() -> None:
    headers = repo_security_headers()
    assert "frame-ancestors 'none'" in headers["Content-Security-Policy"]
    assert headers["X-Frame-Options"] == "DENY"
