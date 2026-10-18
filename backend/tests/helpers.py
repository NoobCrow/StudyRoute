"""Test harness: a fresh app, a fake clock and seeded demo data for every test."""

from __future__ import annotations

import sqlite3
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient
from httpx import Response

from app.api.context import AppContext
from app.audit.chain import GENESIS, HASHED_FIELDS, compute_hash
from app.core.clock import FakeClock
from app.core.config import Settings
from app.domain.constants import ActorKind
from app.domain.rbac import ROLE_PERMISSIONS
from app.main import create_app
from app.scripts.seed import ADMIN_EMAIL, AI_ID, PARENT_EMAIL, STUDENT_EMAIL, seed_demo

START = datetime(2026, 10, 14, 5, 0, tzinfo=UTC)  # Wednesday 11:00 in Dhaka
PASSWORD = "Test-Password-1!"
MFA_CODE = "246810"
EMAILS = {"parent": PARENT_EMAIL, "student": STUDENT_EMAIL, "admin": ADMIN_EMAIL}
UNIVERSITY = "University of Example (synthetic)"


class InProcessDispatcher:
    """Delivers simulator webhooks straight into the app under test."""

    def __init__(self) -> None:
        self.client: TestClient | None = None
        self.sent: list[tuple[bytes, dict[str, str]]] = []

    def post(self, body: bytes, headers: Any) -> int:
        assert self.client is not None
        self.sent.append((body, dict(headers)))
        url = "/api/v1/webhooks/provider"
        return self.client.post(url, content=body, headers=dict(headers)).status_code


def make_settings(tmp_path: Path, **overrides: Any) -> Settings:
    values: dict[str, Any] = {
        "data_dir": tmp_path / "data",
        "database_url": f"sqlite:///{(tmp_path / 'test.db').as_posix()}",
        "rate_limit_enabled": False,
        "simulator_enabled": False,
        "argon2_time_cost": 1,
        "argon2_memory_kib": 8,
        "argon2_parallelism": 1,
        "seed_demo_password": PASSWORD,
        "sandbox_mfa_code": MFA_CODE,
        "nlu_mode": "off",  # the existing tests exercise the rules; new tests switch the reader on
        "dialogue_mode": "off",
        "explainer_mode": "off",  # the small explainer is switched on by the tests that exercise it
        "risk_mode": "off",  # the risk model likewise; without it the plain rules route reviews
        "assistant_cloud_enabled": False,  # deterministic/offline regression harness
    }
    values.update(overrides)
    return Settings(**values)


class WorldBase:
    clock: FakeClock
    client: TestClient
    ctx: AppContext
    ids: dict[str, str]

    def __init__(self, tmp_path: Path, *, bank_network: bool = False, **settings: Any) -> None:
        self.clock = FakeClock(START)
        self.dispatcher = InProcessDispatcher()
        self.settings = make_settings(tmp_path, **settings)
        self.app = create_app(self.settings, self.clock, self.dispatcher)
        self.ctx = self.app.state.ctx
        self.client = TestClient(self.app)
        self.dispatcher.client = self.client
        self.ids = seed_demo(self.ctx, bank_network=bank_network)
        self._tokens: dict[str, tuple[str, datetime]] = {}

    def close(self) -> None:
        self.client.close()
        self.ctx.db.dispose()

    def login(self, who: str, *, fresh: bool = False) -> dict[str, str]:
        cached = self._tokens.get(who)
        if cached and not fresh and cached[1] > self.clock.now():
            return {"Authorization": f"Bearer {cached[0]}"}
        creds = {"email": EMAILS[who], "password": PASSWORD}
        response = self.client.post("/api/v1/auth/login", json=creds)
        assert response.status_code == 200, response.text
        body = response.json()
        expires = self.clock.now() + timedelta(seconds=body["expires_in"] - 5)
        self._tokens[who] = (body["access_token"], expires)
        return {"Authorization": f"Bearer {body['access_token']}"}

    def ai_headers(self, on_behalf_of: str = "parent") -> dict[str, str]:
        scopes = frozenset(p.value for p in ROLE_PERMISSIONS[ActorKind.AI])
        token, _ = self.ctx.tokens.issue(
            user_id=AI_ID,
            kind=ActorKind.AI,
            scopes=scopes,
            now=self.clock.now(),
            act_for=self.ids[on_behalf_of],
        )
        return {"Authorization": f"Bearer {token}"}

    def mfa(self, who: str, scope: str, subject_id: str, code: str = MFA_CODE) -> str:
        response = self.client.post(
            "/api/v1/auth/mfa/verify",
            headers=self.login(who),
            json={"code": code, "scope": scope, "subject_id": subject_id},
        )
        assert response.status_code == 200, response.text
        return str(response.json()["mfa_proof"])

    def call(
        self,
        method: str,
        path: str,
        who: str | None = "parent",
        *,
        json: Any = None,
        idem: bool | str = False,
        mfa: str | None = None,
        headers: dict[str, str] | None = None,
    ) -> Response:
        merged: dict[str, str] = dict(self.login(who)) if who else {}
        if idem:
            merged["Idempotency-Key"] = idem if isinstance(idem, str) else str(uuid.uuid4())
        if mfa:
            merged["X-MFA-Proof"] = mfa
        merged.update(headers or {})
        return self.client.request(method, f"/api/v1{path}", headers=merged, json=json)


class World(WorldBase):
    """Adds the builders most tests need on top of the raw harness."""

    def recipient_id(self, name: str = UNIVERSITY) -> str:
        items = self.call("GET", "/recipients").json()["items"]
        return next(r["recipient_id"] for r in items if r["display_name"] == name)

    def quote(self, **overrides: Any) -> dict[str, Any]:
        body: dict[str, Any] = {
            "target": {"amount_minor": 1_000_000, "currency": "GBP"},
            "purpose": "TUITION",
            "destination_country": "GB",
            "charge_code": "OUR",
            "due_date": "2026-10-28",
        }
        who = overrides.pop("who", "parent")
        body.update(overrides)
        response = self.call("POST", "/quotes", who, json=body)
        assert response.status_code == 201, response.text
        return dict(response.json())

    def draft(self, quote: dict[str, Any] | None = None, **overrides: Any) -> dict[str, Any]:
        quote = quote or self.quote()
        body = {
            "quote_id": quote["quote_id"],
            "provider_id": "prov_b",
            "recipient_id": self.recipient_id(),
            "reference": "INV-2026-4471 / STU-883201",
        }
        body.update(overrides)
        response = self.call("POST", "/payments", "parent", json=body, idem=True)
        assert response.status_code == 201, response.text
        return dict(response.json())

    def verify_kyc(self) -> None:
        review = {"user_id": self.ids["parent"], "status": "VERIFIED"}
        response = self.call("PUT", "/kyc/mock-review", "admin", json=review)
        assert response.status_code == 200, response.text

    def allowlist(self, recipient_id: str | None = None) -> None:
        rid = recipient_id or self.recipient_id()
        proof = self.mfa("parent", "allowlist_recipient", rid)
        response = self.call("PATCH", f"/recipients/{rid}", json={"allowlisted": True}, mfa=proof)
        assert response.status_code == 200, response.text

    def ready_payment(self, **draft_overrides: Any) -> dict[str, Any]:
        """KYC verified, recipient allowlisted, approval requested. Returns the approval body."""
        self.verify_kyc()
        self.allowlist()
        payment = self.draft(**draft_overrides)
        path = f"/payments/{payment['payment_id']}/request-approval"
        response = self.call("POST", path, idem=True)
        assert response.status_code == 200, response.text
        return dict(response.json())

    def approve(self, approval: dict[str, Any], **kwargs: Any) -> Response:
        pid = approval["payment_id"]
        proof = kwargs.pop("mfa", None) or self.mfa("parent", "approve_payment", pid)
        return self.call(
            "POST",
            f"/payments/{pid}/approve",
            json={"confirm_summary_hash": approval["summary_hash"]},
            idem=kwargs.pop("idem", True),
            mfa=proof,
            **kwargs,
        )

    def audit_rows(self, **filters: Any) -> list[dict[str, Any]]:
        items = self.call("GET", "/audit/events?limit=100", "admin").json()["items"]
        return [r for r in items if all(r.get(k) == v for k, v in filters.items())]


def rewrite_audit_consistently(db_path: Path, seq: int, detail: str) -> None:
    """The attack a SHA-256 chain alone cannot catch: edit an event, then recompute every hash
    after it (and the head). The chain still verifies; only an outside anchor notices."""
    con = sqlite3.connect(db_path)
    con.row_factory = sqlite3.Row
    con.execute("DROP TRIGGER IF EXISTS audit_events_no_update")
    rows = [dict(r) for r in con.execute("SELECT * FROM audit_events ORDER BY seq")]
    prev = GENESIS
    for row in rows:
        if row["seq"] == seq:
            row["detail"] = detail
        row["prev_event_hash"] = prev
        row["this_event_hash"] = compute_hash(prev, {k: row[k] for k in HASHED_FIELDS})
        prev = row["this_event_hash"]
        con.execute(
            "UPDATE audit_events SET detail = ?, prev_event_hash = ?, this_event_hash = ?"
            " WHERE seq = ?",
            (row["detail"], row["prev_event_hash"], row["this_event_hash"], row["seq"]),
        )
    con.execute("UPDATE audit_head SET hash = ? WHERE id = 1", (prev,))
    con.commit()
    con.close()
