"""Encrypted per-person BYOK persistence; all provider HTTP is mocked."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.core.crypto import FieldCipher
from app.main import create_app
from app.models import SavedAIConnection
from tests.helpers import World
from tests.test_ai_cloud import KEY, connection, patch_factory

PATH = "/assistant/connection"


def save(world: World, who: str = "parent", **changes: Any):
    return world.call("PUT", PATH, who, json={**connection(), "storage_consent": True, **changes})


@pytest.mark.parametrize("method", ["GET", "PUT", "DELETE"])
def test_requires_authentication(world: World, method: str) -> None:
    result = world.client.request(method, "/api/v1" + PATH, json={})
    assert result.status_code == 401


@pytest.mark.parametrize(
    "changes",
    [
        {"storage_consent": False},
        {"storage_consent": None},
        {"consent": False},
        {"api_key": "x"},
        {"provider": "evil"},
        {"base_url": "http://evil.test"},
    ],
)
def test_explicit_storage_consent_and_safe_validation(world: World, changes: dict) -> None:
    result = save(world, **changes)
    assert result.status_code == 422
    assert KEY not in result.text
    with world.ctx.db.read() as session:
        assert session.get(SavedAIConnection, world.ids["parent"]) is None


def test_storage_consent_cannot_be_omitted(world: World) -> None:
    assert world.call("PUT", PATH, json=connection()).status_code == 422


def test_encrypted_storage_metadata_only_and_chat_resolves_key(
    world: World, monkeypatch, caplog
) -> None:
    keys = patch_factory(monkeypatch)
    result = save(world)
    assert result.status_code == 200, result.text
    assert result.json()["saved"] and result.json()["verified"]
    with world.ctx.db.read() as session:
        row = session.get(SavedAIConnection, world.ids["parent"])
        sealed = row.api_key_enc
        assert sealed.startswith("v1.") and KEY not in sealed
        assert world.ctx.cipher.decrypt(sealed, context=f"saved-ai-key:{row.user_id}:groq") == KEY
    meta = world.call("GET", PATH)
    assert set(meta.json()) == {"saved", "provider", "model", "verified", "updated_at"}
    assert meta.headers["cache-control"] == "no-store"
    assert result.headers["cache-control"] == "no-store"
    count = len(keys)
    chat = world.call("POST", "/assistant/chat", json={"message": "hello"})
    assert chat.json()["mode"] == "llm", chat.text
    assert keys[count:] == [KEY]
    for value in [result.text, meta.text, chat.text, caplog.text, json.dumps(world.audit_rows())]:
        assert KEY not in value and sealed not in value
    # No plaintext in SQLite, including WAL content.
    for path in Path(world.settings.database_url.removeprefix("sqlite:///")).parent.glob(
        "test.db*"
    ):
        assert KEY.encode() not in path.read_bytes()


def test_saved_key_survives_new_application_and_fresh_login(world: World, monkeypatch) -> None:
    keys = patch_factory(monkeypatch)
    assert save(world).json()["saved"]
    app = create_app(world.settings, world.clock)
    try:
        with TestClient(app) as client:
            from tests.helpers import EMAILS, PASSWORD

            token = client.post(
                "/api/v1/auth/login", json={"email": EMAILS["parent"], "password": PASSWORD}
            ).json()["access_token"]
            headers = {"Authorization": f"Bearer {token}"}
            assert client.get("/api/v1" + PATH, headers=headers).json()["saved"]
            count = len(keys)
            chat = client.post("/api/v1/assistant/chat", headers=headers, json={"message": "hello"})
            assert chat.json()["mode"] == "llm", chat.text
            assert keys[count:] == [KEY]
    finally:
        app.state.ctx.db.dispose()


def test_keys_are_personal_not_household_or_delegated(world: World, monkeypatch) -> None:
    keys = patch_factory(monkeypatch)
    save(world)
    assert world.call("GET", PATH, "student").json() == {"saved": False}
    # Administrators do not gain CHAT_USE or access to any saved personal key.
    assert world.call("GET", PATH, "admin").status_code == 403
    student_key = "gsk_synthetic_student_personal_key"
    save(world, "student", api_key=student_key)
    count = len(keys)
    world.call("POST", "/assistant/chat", "student", json={"message": "hello"})
    world.call("POST", "/assistant/chat", "parent", json={"message": "hello"})
    assert keys[count:] == [student_key, KEY]
    for method in ["GET", "PUT", "DELETE"]:
        result = world.call(
            method,
            PATH,
            None,
            headers=world.ai_headers(),
            json={**connection(), "storage_consent": True},
        )
        assert result.status_code == 403
    count = len(keys)
    world.call(
        "POST", "/assistant/chat", None, headers=world.ai_headers(), json={"message": "hello"}
    )
    assert len(keys) == count
    world.call("DELETE", PATH, "parent")
    assert world.call("GET", PATH, "student").json()["saved"]


def test_invalid_replacement_preserves_previous_saved_key(world: World, monkeypatch) -> None:
    patch_factory(monkeypatch)
    save(world)
    with world.ctx.db.read() as session:
        sealed = session.get(SavedAIConnection, world.ids["parent"]).api_key_enc
    patch_factory(monkeypatch, status=401)
    failed = save(world, api_key=KEY + "_invalid_replacement")
    assert not failed.json()["ok"] and not failed.json()["saved"]
    with world.ctx.db.read() as session:
        assert session.get(SavedAIConnection, world.ids["parent"]).api_key_enc == sealed


def test_quota_failure_can_save_honestly_without_default_fallback(
    world: World, monkeypatch
) -> None:
    patch_factory(monkeypatch, status=429)
    result = save(world).json()
    assert result["ok"] and result["saved"] and not result["verified"]
    assert result["availability"]["code"] == "quota_exhausted"
    chat = world.call("POST", "/assistant/chat", json={"message": "hello"}).json()
    assert chat["mode"] == "unavailable"
    assert chat["availability"]["provider"] == "groq"
    assert chat["availability"]["code"] == "quota_exhausted"


@pytest.mark.parametrize("tamper", ["master", "provider", "ciphertext"])
def test_decryption_failure_is_actionable_not_silent_fallback(
    world: World, monkeypatch, tamper: str
) -> None:
    keys = patch_factory(monkeypatch)
    save(world)
    if tamper == "master":
        world.ctx.cipher = FieldCipher(b"x" * 32)
    else:
        with world.ctx.db.write() as session:
            row = session.get(SavedAIConnection, world.ids["parent"])
            if tamper == "provider":
                row.provider = "gemini"
            else:
                row.api_key_enc = "v1.broken"
    count = len(keys)
    result = world.call("POST", "/assistant/chat", json={"message": "hello"})
    assert result.status_code == 409, result.text
    assert "cannot be decrypted" in result.text
    assert len(keys) == count
    assert world.call("DELETE", PATH).json()["removed"]


def test_explicit_override_is_compatible_and_delete_restores_default(
    world: World, monkeypatch
) -> None:
    keys = patch_factory(monkeypatch)
    save(world)
    count = len(keys)
    override = {**connection(), "api_key": "gsk_synthetic_one_request_key"}
    world.call("POST", "/assistant/chat", json={"message": "hello", "connection": override})
    assert keys[count:] == [override["api_key"]]
    for _ in range(2):
        deleted = world.call("DELETE", PATH)
        assert deleted.json()["removed"] and deleted.headers["cache-control"] == "no-store"
    assert world.call("GET", PATH).json() == {"saved": False}
    world.ctx.settings.assistant_cloud_enabled = True
    chat = world.call("POST", "/assistant/chat", json={"message": "hello"}).json()
    assert chat["availability"]["code"] == "not_configured"


def test_reset_removes_only_callers_personal_key(world: World, monkeypatch) -> None:
    patch_factory(monkeypatch)
    save(world)
    save(world, "student", api_key=KEY + "_student_reset")
    result = world.call("POST", "/me/reset")
    assert result.status_code == 200, result.text
    assert world.call("GET", PATH).json() == {"saved": False}
    assert world.call("GET", PATH, "student").json()["saved"]
