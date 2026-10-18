"""Login, lockout, token rules and the auth rate limit (T22)."""

from __future__ import annotations

import base64
import json
from pathlib import Path

import jwt
from cryptography.hazmat.primitives.asymmetric import ec
from sqlalchemy import text

from tests.helpers import EMAILS, PASSWORD, World


def login(world: World, email: str, password: str):
    return world.client.post("/api/v1/auth/login", json={"email": email, "password": password})


def test_login_returns_short_lived_es256_tokens_and_the_user(world: World) -> None:
    body = login(world, EMAILS["parent"], PASSWORD).json()
    assert body["token_type"] == "Bearer"
    assert body["expires_in"] == 900
    assert body["user"]["role"] == "parent"
    assert body["user"]["kyc_status"] == "NEEDS_DOCUMENTS"
    header = jwt.get_unverified_header(body["access_token"])
    assert header["alg"] == "ES256"
    claims = jwt.decode(body["access_token"], options={"verify_signature": False})
    assert claims["exp"] - claims["iat"] == 900
    assert {"sub", "role", "scope", "exp", "jti"} <= set(claims)
    assert "payments:approve" in claims["scope"].split()
    assert world.audit_rows(action="auth.login")


def test_passwords_and_mfa_secrets_are_stored_hashed_and_encrypted(world: World) -> None:
    with world.ctx.db.read() as session:
        row = session.execute(
            text("SELECT password_hash, mfa_secret_enc FROM users WHERE email = :e"),
            {"e": EMAILS["parent"]},
        ).one()
    assert row[0].startswith("$argon2id$")
    assert PASSWORD not in row[0]
    assert row[1].startswith("v1.")


def test_wrong_password_and_unknown_user_look_identical(world: World) -> None:
    wrong = login(world, EMAILS["parent"], "nope-nope")
    unknown = login(world, "nobody@demo.studyroute.test", "nope-nope")
    assert wrong.status_code == unknown.status_code == 401
    assert wrong.json()["detail"] == unknown.json()["detail"]
    failed = world.audit_rows(action="auth.failed")
    assert len(failed) == 2
    assert "nobody@" not in json.dumps(failed)


def test_the_ai_service_account_cannot_log_in(world: World) -> None:
    assert login(world, "ai-agent@demo.studyroute.test", PASSWORD).status_code == 401


def test_repeated_failures_lock_the_account_for_a_while(world: World) -> None:
    for _ in range(5):
        assert login(world, EMAILS["parent"], "wrong-password").status_code == 401
    locked = login(world, EMAILS["parent"], PASSWORD)
    assert locked.status_code == 429
    assert int(locked.headers["retry-after"]) > 0
    world.clock.advance(901)
    assert login(world, EMAILS["parent"], PASSWORD).status_code == 200


def test_T22_a_burst_of_logins_gets_429_with_retry_after(tmp_path: Path) -> None:
    world = World(tmp_path, rate_limit_enabled=True)
    try:
        # a different address each time, so only the per-IP limit (not an account lockout) applies
        codes = [login(world, f"user{n}@demo.studyroute.test", "wrong-password") for n in range(50)]
        statuses = [r.status_code for r in codes]
        assert statuses[:10] == [401] * 10
        assert set(statuses[10:]) == {429}
        assert int(codes[-1].headers["retry-after"]) >= 1
        assert codes[-1].json()["code"] == "RATE_LIMITED"
        world.clock.advance(61)
        assert login(world, EMAILS["student"], PASSWORD).status_code == 200
    finally:
        world.close()


def test_refresh_tokens_rotate_and_reuse_revokes_the_whole_family(world: World) -> None:
    first = login(world, EMAILS["parent"], PASSWORD).json()
    refreshed = world.client.post(
        "/api/v1/auth/refresh", json={"refresh_token": first["refresh_token"]}
    )
    assert refreshed.status_code == 200
    second = refreshed.json()
    assert second["refresh_token"] != first["refresh_token"]
    reuse = world.client.post(
        "/api/v1/auth/refresh", json={"refresh_token": first["refresh_token"]}
    )
    assert reuse.status_code == 401
    after = world.client.post(
        "/api/v1/auth/refresh", json={"refresh_token": second["refresh_token"]}
    )
    assert after.status_code == 401


def test_logout_revokes_the_refresh_token(world: World) -> None:
    tokens = login(world, EMAILS["parent"], PASSWORD).json()
    refresh = {"refresh_token": tokens["refresh_token"]}
    assert world.client.post("/api/v1/auth/logout", json=refresh).status_code == 200
    assert world.client.post("/api/v1/auth/refresh", json=refresh).status_code == 401


def test_access_tokens_expire_after_fifteen_minutes(world: World) -> None:
    headers = world.login("parent")
    assert world.client.get("/api/v1/me", headers=headers).status_code == 200
    world.clock.advance(901)
    assert world.client.get("/api/v1/me", headers=headers).status_code == 401


def test_forged_tampered_and_unsigned_tokens_are_rejected(world: World) -> None:
    good = world.login("student")["Authorization"].split()[1]
    header, payload, signature = good.split(".")
    claims = json.loads(base64.urlsafe_b64decode(payload + "=="))
    claims["role"] = "parent"
    forged_payload = base64.urlsafe_b64encode(json.dumps(claims).encode()).rstrip(b"=").decode()
    candidates = {
        "payload swapped": f"{header}.{forged_payload}.{signature}",
        "no signature": f"{header}.{payload}.",
        "alg none": jwt.encode(claims, key="", algorithm="none"),
        "other key": jwt.encode(
            {**claims, "aud": "studyroute-api", "iss": "studyroute-sandbox"},
            ec.generate_private_key(ec.SECP256R1()),
            algorithm="ES256",
        ),
        "garbage": "not.a.token",
    }
    for name, token in candidates.items():
        response = world.client.get("/api/v1/me", headers={"Authorization": f"Bearer {token}"})
        assert response.status_code == 401, name


def test_missing_or_wrong_scheme_is_401(world: World) -> None:
    assert world.client.get("/api/v1/me").status_code == 401
    assert world.client.get("/api/v1/me", headers={"Authorization": "Basic abc"}).status_code == 401


def test_real_and_made_up_addresses_lock_the_same_way_so_accounts_cannot_be_discovered(
    world: World,
) -> None:
    """After repeated failures a real account answered 429 while an unknown address kept answering
    401, which told an attacker which e-mail addresses have accounts. Both must now look alike."""

    def burst(email: str) -> list[int]:
        return [login(world, email, "wrong-password").status_code for _ in range(7)]

    real, unknown = burst(EMAILS["student"]), burst("nobody@nowhere.test")
    assert real == unknown == [401] * 5 + [429] * 2
    a, b = login(world, EMAILS["student"], "x"), login(world, "nobody@nowhere.test", "x")
    assert a.status_code == b.status_code == 429
    assert a.json()["detail"] == b.json()["detail"] and a.json()["code"] == b.json()["code"]
    assert a.headers["retry-after"] == b.headers["retry-after"]
    assert login(world, EMAILS["student"], PASSWORD).status_code == 429, (
        "even the right password waits"
    )
    world.clock.advance(901)
    assert login(world, EMAILS["student"], PASSWORD).status_code == 200
    assert login(world, "nobody@nowhere.test", "x").status_code == 401, "the lock expired for both"


def test_a_good_sign_in_resets_the_failure_count(world: World) -> None:
    for _ in range(4):
        assert login(world, EMAILS["parent"], "wrong-password").status_code == 401
    assert login(world, EMAILS["parent"], PASSWORD).status_code == 200
    for _ in range(4):
        assert login(world, EMAILS["parent"], "wrong-password").status_code == 401, "a fresh count"


def test_the_failed_login_table_cannot_be_grown_without_limit() -> None:
    from datetime import UTC, datetime

    from app.core.clock import FakeClock
    from app.domain.auth import FailedLoginTracker

    tracker = FailedLoginTracker(FakeClock(datetime(2026, 10, 14, tzinfo=UTC)), 5, 900)
    for n in range(FailedLoginTracker.MAX_ENTRIES + 3_000):
        tracker.fail(f"made-up-{n}")
    assert len(tracker._entries) <= FailedLoginTracker.MAX_ENTRIES
