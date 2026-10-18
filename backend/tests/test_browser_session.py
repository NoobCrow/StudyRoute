"""Browser cookie security and multi-tab regression tests (no real credentials)."""

from concurrent.futures import ThreadPoolExecutor

import pytest

from app.core.browser_session import COOKIE
from app.models import BrowserSession
from tests.helpers import EMAILS, PASSWORD

HEADERS = {"Origin": "http://testserver", "X-StudyRoute-Browser": "1"}
BASE = "/api/v1/auth/browser"


def login(world, who="parent"):
    response = world.client.post(
        BASE + "/login", json={"email": EMAILS[who], "password": PASSWORD}, headers=HEADERS
    )
    assert response.status_code == 200, response.text
    return response


def restore(world, headers=None):
    return world.client.post(
        BASE + "/session", json={}, headers=HEADERS if headers is None else headers
    )


def test_cookie_is_httponly_host_only_and_not_returned_as_refresh(world):
    response = login(world)
    cookie = response.headers["set-cookie"]
    assert "HttpOnly" in cookie and "SameSite=strict" in cookie and "Path=/api/v1" in cookie
    assert "Domain=" not in cookie and "Max-Age=" in cookie
    assert "refresh_token" not in response.json()
    assert response.headers["cache-control"] == "no-store"
    raw = world.client.cookies[COOKIE]
    with world.ctx.db.read() as db:
        rows = db.query(BrowserSession).all()
        assert len(rows) == 1 and rows[0].token_hash != raw


def test_new_tabs_and_concurrent_restore_do_not_rotate_or_revoke_cookie(world):
    login(world)
    cookie = world.client.cookies[COOKIE]
    with ThreadPoolExecutor(max_workers=5) as pool:
        responses = list(pool.map(lambda _: restore(world), range(10)))
    assert all(r.status_code == 200 for r in responses)
    assert world.client.cookies[COOKIE] == cookie
    assert all("set-cookie" not in r.headers for r in responses)
    assert all(r.headers["cache-control"] == "no-store" for r in responses)


def test_logout_revokes_already_issued_access_and_copied_cookie(world):
    token = login(world).json()["access_token"]
    cookie = world.client.cookies[COOKIE]
    bearer = {"Authorization": "Bearer " + token}
    assert world.client.get("/api/v1/me", headers=bearer).status_code == 200
    assert world.client.post(BASE + "/logout", json={}, headers=HEADERS).status_code == 200
    world.client.cookies.set(COOKIE, cookie)
    assert restore(world).status_code == 401
    assert world.client.get("/api/v1/me", headers=bearer).status_code == 401


def test_cookie_binding_prevents_bearer_only_use(world):
    token = login(world).json()["access_token"]
    world.client.cookies.clear()
    assert (
        world.client.get("/api/v1/me", headers={"Authorization": "Bearer " + token}).status_code
        == 401
    )


def test_account_switch_revokes_previous_browser_account(world):
    old = login(world).json()["access_token"]
    new = login(world, "student").json()
    assert new["user"]["role"] == "student"
    assert (
        world.client.get("/api/v1/me", headers={"Authorization": "Bearer " + old}).status_code
        == 401
    )
    assert restore(world).json()["user"]["role"] == "student"


@pytest.mark.parametrize(
    "headers",
    [
        {},
        {"Origin": "http://testserver"},
        {"X-StudyRoute-Browser": "1"},
        {**HEADERS, "Origin": "https://evil.test"},
        {**HEADERS, "Origin": "null"},
        {**HEADERS, "Sec-Fetch-Site": "cross-site"},
    ],
)
@pytest.mark.parametrize("path", ["login", "session", "logout"])
def test_csrf_rejected_without_exact_origin_and_header(world, headers, path):
    login(world)
    body = {"email": EMAILS["parent"], "password": PASSWORD} if path == "login" else {}
    assert world.client.post(BASE + "/" + path, json=body, headers=headers).status_code == 403
    assert restore(world).status_code == 200


def test_absolute_expiry_is_not_extended_by_restore(world):
    login(world)
    before = restore(world).json()["session_expires_at"]
    world.clock.advance(60)
    assert restore(world).json()["session_expires_at"] == before
    world.clock.advance(world.settings.refresh_token_ttl_seconds)
    assert restore(world).status_code == 401


def test_legacy_refresh_api_still_rotates(world):
    response = world.client.post(
        "/api/v1/auth/login", json={"email": EMAILS["parent"], "password": PASSWORD}
    )
    token = response.json()["refresh_token"]
    assert (
        world.client.post("/api/v1/auth/refresh", json={"refresh_token": token}).status_code == 200
    )
    assert (
        world.client.post("/api/v1/auth/refresh", json={"refresh_token": token}).status_code == 401
    )


def test_cookie_secure_flag_in_https_and_production(world):
    from types import SimpleNamespace

    from starlette.requests import Request
    from starlette.responses import Response

    from app.core.browser_session import set_cookie

    request = Request(
        {
            "type": "http",
            "scheme": "https",
            "server": ("testserver", 443),
            "path": "/",
            "headers": [],
        }
    )
    response = Response()
    set_cookie(response, request, world.ctx, "short-synthetic")
    assert "Secure" in response.headers["set-cookie"]
    world.ctx.settings = SimpleNamespace(is_sandbox=False, refresh_token_ttl_seconds=3600)
    request = Request(
        {"type": "http", "scheme": "http", "server": ("testserver", 80), "path": "/", "headers": []}
    )
    response = Response()
    set_cookie(response, request, world.ctx, "short-synthetic")
    assert "Secure" in response.headers["set-cookie"]


def test_tab_restore_has_separate_budget_and_does_not_block_logout(world):
    from app.api.rate_limit import RateLimiter

    world.ctx.limiter = RateLimiter(world.clock, enabled=True)
    login(world)
    for _ in range(15):
        assert restore(world).status_code == 200
    assert world.client.post(BASE + "/logout", json={}, headers=HEADERS).status_code == 200
    # Fifteen restores did not consume the brute-force login budget.
    login(world)


def test_cookie_restore_limit_still_reports_retry_after(world):
    from app.api.rate_limit import RateLimiter

    world.ctx.limiter = RateLimiter(world.clock, enabled=True)
    login(world)
    for _ in range(60):
        assert restore(world).status_code == 200
    blocked = restore(world)
    assert blocked.status_code == 429
    assert int(blocked.headers["retry-after"]) > 0
    # Logout is still possible even if the restore bucket was exhausted.
    assert world.client.post(BASE + "/logout", json={}, headers=HEADERS).status_code == 200
