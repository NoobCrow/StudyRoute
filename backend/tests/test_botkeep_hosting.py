"""GitHub deployment: same-origin routes, security and persistence (no live providers)."""

from __future__ import annotations

import base64
import hashlib
import json

import pytest
from fastapi.testclient import TestClient

from app import hosting
from app.core.browser_session import COOKIE
from app.core.config import Settings
from app.core.demo import PARENT_EMAIL


@pytest.fixture
def hosted(tmp_path, monkeypatch):
    root = tmp_path / "site"
    (root / "login").mkdir(parents=True)
    (root / "_next" / "static").mkdir(parents=True)
    for path in (root / "index.html", root / "login" / "index.html"):
        path.write_text('<html><body>StudyRoute<script>console.log("boot")</script></body></html>')
    (root / "404.html").write_text("Not found")
    (root / "_next" / "static" / "asset.js").write_text('console.log("asset")')
    digest = base64.b64encode(hashlib.sha256(b'console.log("boot")').digest()).decode()
    (root / "csp-hashes.json").write_text(json.dumps({"hashes": [f"'sha256-{digest}'"]}))
    settings = Settings(
        data_dir=tmp_path / "persistent",
        public_origin="https://demo.test",
        assistant_cloud_enabled=False,
        simulator_enabled=False,
        rate_limit_enabled=False,
        nlu_mode="off",
        dialogue_mode="off",
        explainer_mode="off",
        risk_mode="off",
    )
    monkeypatch.setenv("STUDYROUTE_STATIC_DIR", str(root))
    monkeypatch.setattr(hosting, "get_settings", lambda: settings)
    return settings, root


def test_frontend_api_security_and_missing_routes(hosted):
    app = hosting.create_app()
    with TestClient(app, base_url="https://demo.test") as client:
        page = client.get("/login/")
        assert page.status_code == 200
        assert "'sha256-" in page.headers["content-security-policy"]
        assert "unsafe-inline" not in page.headers["content-security-policy"]
        assert page.headers["x-content-type-options"] == "nosniff"
        assert page.headers["cache-control"] == "no-store"
        api = client.get("/api/v1/health")
        assert api.status_code == 200
        assert "default-src 'none'" in api.headers["content-security-policy"]
        asset = client.get("/_next/static/asset.js")
        assert asset.status_code == 200 and "immutable" in asset.headers["cache-control"]
        for path in ("/api/v1/not-a-route", "/.env", "/data/studyroute.db", "/missing/"):
            assert client.get(path).status_code == 404
        redirect = client.get("/login", follow_redirects=False)
        assert redirect.status_code == 307 and redirect.headers["location"] == "/login/"


def test_cookie_survives_restart_new_tab_and_no_reseed_reset(hosted):
    headers = {"Origin": "https://demo.test", "X-StudyRoute-Browser": "1"}
    app = hosting.create_app()
    with TestClient(app, base_url="https://demo.test") as client:
        response = client.post(
            "/api/v1/auth/browser/login",
            headers=headers,
            json={"email": PARENT_EMAIL, "password": app.state.ctx.settings.demo_password},
        )
        assert response.status_code == 200, response.text
        assert "Secure" in response.headers["set-cookie"]
        cookie = client.cookies[COOKIE]
    again = hosting.create_app()
    with TestClient(again, base_url="https://demo.test") as client:
        client.cookies.set(COOKIE, cookie)
        for _ in range(3):
            response = client.post("/api/v1/auth/browser/session", headers=headers, json={})
            assert response.status_code == 200, response.text
            assert "set-cookie" not in response.headers
        response = client.post(
            "/api/v1/auth/browser/session",
            json={},
            headers={**headers, "Origin": "https://evil.test"},
        )
        assert response.status_code == 403


def test_https_cookie_secure_even_when_proxy_upstream_is_http(hosted):
    app = hosting.create_app()
    with TestClient(app, base_url="http://internal.test") as client:
        response = client.post(
            "/api/v1/auth/browser/login",
            headers={"Origin": "https://demo.test", "X-StudyRoute-Browser": "1"},
            json={"email": PARENT_EMAIL, "password": app.state.ctx.settings.demo_password},
        )
        assert response.status_code == 200
        assert "Secure" in response.headers["set-cookie"]


def test_invalid_build_fails_closed(hosted):
    _, root = hosted
    (root / "csp-hashes.json").write_text(json.dumps({"hashes": ["unsafe-inline"]}))
    with pytest.raises(RuntimeError, match="CSP"):
        hosting.create_app()
    (root / "login" / "index.html").unlink()
    with pytest.raises(RuntimeError, match="frontend missing"):
        hosting.create_app()


@pytest.mark.parametrize("origin", ["*", "https://demo.test/path", "https://user@demo.test"])
def test_bad_public_origin_fails_validation(origin):
    with pytest.raises(ValueError, match="PUBLIC_ORIGIN"):
        Settings(public_origin=origin)
