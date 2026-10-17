"""Smoke-test a running StudyRoute stack: the web server, the API behind it and their headers.

    python scripts/docker_smoke.py                     # http://localhost:8080 (docker compose up)
    python scripts/docker_smoke.py http://localhost:8080
    python scripts/docker_smoke.py http://127.0.0.1:8000 --api-only

Standard library only, so it runs on the host, in CI, or anywhere Python 3 is installed. Every
check prints OK or FAIL and the exit code is 1 if any check failed. It reads nothing private and
changes nothing: it only sends GET requests and one oversized POST that must be refused.
"""

from __future__ import annotations

import argparse
import http.client
import json
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass

TIMEOUT = 10


@dataclass
class Reply:
    status: int
    headers: dict[str, list[str]]
    body: bytes

    def header(self, name: str) -> str:
        return ", ".join(self.headers.get(name.lower(), []))

    def count(self, name: str) -> int:
        """How many times the server sent this header (a duplicated security header is a smell)."""
        return len(self.headers.get(name.lower(), []))

    def json(self) -> dict[str, object]:
        data = json.loads(self.body.decode("utf-8"))
        return data if isinstance(data, dict) else {}


def fetch(url: str, method: str = "GET", data: bytes | None = None) -> Reply:
    request = urllib.request.Request(url, data=data, method=method)  # noqa: S310 (http only)
    if data is not None:
        request.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT) as response:  # noqa: S310
            return Reply(response.status, _lower(response.headers.items()), response.read())
    except urllib.error.HTTPError as error:
        return Reply(error.code, _lower(error.headers.items()), error.read())


def _lower(items: object) -> dict[str, list[str]]:
    grouped: dict[str, list[str]] = {}
    for name, value in items:  # type: ignore[attr-defined]
        grouped.setdefault(str(name).lower(), []).append(str(value))
    return grouped


def status_for_oversized_body(base: str) -> int:
    """POST that *declares* a 200 KB body and sends none. A server that enforces its size limit
    answers 413 from the header alone, so there is nothing to race against."""
    parts = urllib.parse.urlsplit(base)
    connection = http.client.HTTPConnection(
        parts.hostname or "localhost", parts.port or 80, timeout=TIMEOUT
    )
    try:
        connection.putrequest("POST", "/api/v1/auth/login")
        connection.putheader("Content-Type", "application/json")
        connection.putheader("Content-Length", "200000")
        connection.endheaders()
        return connection.getresponse().status
    finally:
        connection.close()


class Report:
    def __init__(self) -> None:
        self.failures: list[str] = []

    def check(self, ok: bool, message: str) -> None:
        print(f"  {'OK  ' if ok else 'FAIL'} {message}")
        if not ok:
            self.failures.append(message)


def check_api(base: str, report: Report) -> None:
    print("The API")
    health = fetch(f"{base}/health")
    report.check(health.status == 200, "GET /health answers 200")
    body = health.json() if health.status == 200 else {}
    report.check(body.get("status") == "ok", "health says status ok")
    report.check(body.get("mode") == "sandbox", "the stack runs in sandbox mode")
    report.check(health.header("x-sandbox") == "true", "every response carries X-Sandbox: true")

    sandbox = fetch(f"{base}/api/v1/sandbox")
    scenarios = {s.get("token") for s in sandbox.json().get("scenarios", [])}  # type: ignore[union-attr]
    report.check(
        sandbox.status == 200 and {"FAIL_TEST", "SLOW_TEST", "SANCTION_TEST"} <= scenarios,
        "GET /api/v1/sandbox lists the test scenarios",
    )
    anonymous = fetch(f"{base}/api/v1/me")
    report.check(anonymous.status == 401, "an unauthenticated request is refused with 401")
    report.check(
        "problem+json" in anonymous.header("content-type"), "errors use RFC 7807 problem+json"
    )
    report.check(bool(anonymous.header("x-request-id")), "every response carries an X-Request-Id")
    api = fetch(f"{base}/api/v1/health")
    report.check(
        "default-src 'none'" in api.header("content-security-policy"),
        "API responses carry a locked-down CSP",
    )
    report.check(
        all(
            api.count(h) <= 1
            for h in (
                "content-security-policy",
                "x-content-type-options",
                "x-frame-options",
                "referrer-policy",
                "strict-transport-security",
            )
        ),
        "each API security header is sent once, not twice",
    )
    report.check(
        status_for_oversized_body(base) == 413, "an oversized request body is refused with 413"
    )


# The exported page names its Next.js bundles under /_next/static/.
def is_app_shell(body: bytes) -> bool:
    return b"/_next/static/" in body


def check_web(base: str, report: Report) -> None:
    print("The web server")
    index = fetch(f"{base}/")
    report.check(index.status == 200, "GET / answers 200")
    report.check("text/html" in index.header("content-type"), "the page is served as HTML")
    report.check(is_app_shell(index.body), "the app shell is present")
    csp = index.header("content-security-policy")
    report.check(
        "default-src 'self'" in csp
        and "frame-ancestors 'none'" in csp
        and "'unsafe-inline'" not in csp,
        "CSP: default-src 'self', no framing, no inline script or style",
    )
    report.check(
        index.header("x-content-type-options") == "nosniff", "X-Content-Type-Options: nosniff"
    )
    report.check(index.header("referrer-policy") == "no-referrer", "Referrer-Policy: no-referrer")
    report.check(index.header("x-frame-options").upper() == "DENY", "X-Frame-Options: DENY")
    report.check("max-age" in index.header("strict-transport-security"), "HSTS is sent")
    report.check("camera=()" in index.header("permissions-policy"), "Permissions-Policy is sent")
    report.check(
        "/" not in index.header("server").split(" ")[0], "the server does not reveal its version"
    )

    deep = fetch(f"{base}/payments")
    report.check(
        deep.status == 200 and is_app_shell(deep.body), "a deep link falls back to the app"
    )
    asset = re.search(r'src="(/_next/static/[^"]+\.js)"', index.body.decode("utf-8", "replace"))
    report.check(asset is not None, "the page references a built JavaScript asset")
    if asset:
        script = fetch(f"{base}{asset.group(1)}")
        report.check(script.status == 200, "the JavaScript asset is served")
        report.check(
            "immutable" in script.header("cache-control"), "assets are cached as immutable"
        )
        report.check(
            "default-src 'self'" in script.header("content-security-policy"),
            "assets carry the security headers too",
        )

    print("The API through the web server")
    check_api(base, report)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawTextHelpFormatter
    )
    parser.add_argument("base_url", nargs="?", default="http://localhost:8080")
    parser.add_argument(
        "--api-only", action="store_true", help="the URL is the API itself, not the web server"
    )
    args = parser.parse_args(argv)
    base = args.base_url.rstrip("/")
    report = Report()
    print(f"StudyRoute smoke test against {base}")
    try:
        if args.api_only:
            check_api(base, report)
        else:
            check_web(base, report)
    except (urllib.error.URLError, OSError) as error:
        print(f"\nCould not reach {base}: {error}", file=sys.stderr)
        print("Is the stack running? Try: docker compose up --build", file=sys.stderr)
        return 2
    if report.failures:
        print(f"\n{len(report.failures)} check(s) failed.", file=sys.stderr)
        return 1
    print("\nAll smoke checks passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
