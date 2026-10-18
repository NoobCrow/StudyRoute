"""Two unrelated households: nothing crosses between them.

The household is the security boundary of the product. A second family signs in and tries to read,
change or borrow the first family's records, MFA proofs and idempotency keys. Everything must
answer 403 or 404 and reveal nothing.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterator
from datetime import timedelta
from pathlib import Path
from typing import Any

import pytest

from app.domain.auth import create_user, human_actor
from app.domain.constants import ActorKind
from app.domain.recipients import RecipientCreate
from app.domain.rules import load_rules
from tests.helpers import EMAILS, PASSWORD, World

SECRET_REFERENCE = "INV-H1-SECRET-REF"
SECRET_ESCROW = "H1-SECRET-ESCROW"
SECRET_DOCUMENT = "H1 SECRET DOCUMENT BODY"
SECRET_TRANSFER = "H1-SECRET-TRANSFER"
DENIED = (401, 403, 404, 422)


@pytest.fixture
def world(tmp_path: Path) -> Iterator[World]:
    """The demo household (household 1) plus an unrelated household 2, with the bank network."""
    instance = World(tmp_path, bank_network=True)
    with instance.ctx.db.write() as session:
        common = {
            "passwords": instance.ctx.passwords,
            "cipher": instance.ctx.cipher,
            "now": instance.clock.now(),
        }
        parent2 = create_user(
            session, **common, user_id="usr_two_parent", email="parent2@lab.studyroute.test",
            display_name="Parent Two", role=ActorKind.PARENT, password=PASSWORD, kyc_status="VERIFIED",
        )  # fmt: skip
        create_user(
            session, **common, user_id="usr_two_student", email="student2@lab.studyroute.test",
            display_name="Student Two", role=ActorKind.STUDENT, password=PASSWORD, parent_id=parent2.id,
        )  # fmt: skip
        instance.ctx.recipients.create(
            session, human_actor(parent2), load_rules(session),
            RecipientCreate(type="UNIVERSITY", display_name="Second Household College (synthetic)",
                            country="GB", bic="WESTGB2L", iban="GB82WEST12345698765432"),
        )  # fmt: skip
    EMAILS["parent2"] = "parent2@lab.studyroute.test"
    EMAILS["student2"] = "student2@lab.studyroute.test"
    yield instance
    EMAILS.pop("parent2", None)
    EMAILS.pop("student2", None)
    instance.close()


class Records:
    """Household 1's private records, created once."""

    def __init__(self, world: World) -> None:
        world.verify_kyc()
        self.quote = world.quote()
        self.payment = world.draft(self.quote, reference=SECRET_REFERENCE)
        first = (world.clock.now() + timedelta(days=3)).date().isoformat()
        escrow = world.call("POST", "/escrows", json={
            "recipient_id": world.recipient_id(), "purpose": "TUITION",
            "total": {"amount_minor": 1_000_000, "currency": "GBP"}, "tranches": 1,
            "first_release": first, "cadence": "ONCE", "reference": SECRET_ESCROW,
        }, idem=True)  # fmt: skip
        assert escrow.status_code == 201, escrow.text
        self.escrow = escrow.json()["escrow_id"]
        document = world.call("POST", "/documents", json={
            "kind": "passport", "filename": "h1-secret-passport.txt", "content_text": SECRET_DOCUMENT,
        })  # fmt: skip
        self.document = document.json()["document_id"]
        accounts = world.call("GET", "/bank/accounts").json()["items"]
        self.account = accounts[0]
        transfer = world.call("POST", "/bank/transfers", json={
            "source": self.account["number"], "destination": "SBX-B-0002",
            "amount": {"amount_minor": 50_000, "currency": "BDT"}, "reference": SECRET_TRANSFER,
        }, idem=True)  # fmt: skip
        assert transfer.status_code == 201, transfer.text
        self.transfer = transfer.json()["id"]
        self.recipient = world.recipient_id()

    @property
    def secrets(self) -> list[str]:
        return [SECRET_REFERENCE, SECRET_ESCROW, SECRET_DOCUMENT, SECRET_TRANSFER,
                "parent@demo.studyroute.test", "GB08EXMP12345612344821"]  # fmt: skip

    @property
    def ids(self) -> list[str]:
        return [
            self.quote["quote_id"],
            self.payment["payment_id"],
            self.escrow,
            self.document,
            self.transfer,
            self.recipient,
        ]


def refused(reply: Any, *secrets: str) -> None:
    assert reply.status_code in DENIED, (
        reply.request.method,
        reply.request.url.path,
        reply.status_code,
    )
    for text in secrets:
        assert text not in reply.text


@pytest.mark.parametrize("outsider", ["parent2", "student2"])
def test_another_household_cannot_read_a_single_record(world: World, outsider: str) -> None:
    h1 = Records(world)
    for path in (
        f"/payments/{h1.payment['payment_id']}", f"/payments/{h1.payment['payment_id']}/tracker",
        f"/payments/{h1.payment['payment_id']}/compliance-report",
        f"/payments/{h1.payment['payment_id']}/instruction-preview", f"/quotes/{h1.quote['quote_id']}",
        f"/escrows/{h1.escrow}", f"/bank/transfers/{h1.transfer}",
        f"/bank/accounts/{h1.account['id']}/statement",
    ):  # fmt: skip
        refused(world.call("GET", path, outsider), *h1.secrets)


def test_another_household_cannot_change_a_single_record(world: World) -> None:
    h1 = Records(world)
    pid = h1.payment["payment_id"]
    attacks = [
        world.call("PATCH", f"/recipients/{h1.recipient}", "parent2", json={"display_name": "Hacked"}),
        world.call("POST", f"/payments/{pid}/cancel", "parent2", idem=True),
        world.call("POST", f"/payments/{pid}/request-approval", "parent2", idem=True),
        world.call("POST", f"/escrows/{h1.escrow}/abandon", "parent2", idem=True),
        world.call("POST", f"/escrows/{h1.escrow}/cancel", "parent2", idem=True),
        world.call("DELETE", f"/documents/{h1.document}", "parent2"),
        world.call("POST", f"/bank/transfers/{h1.transfer}/confirm", "parent2", idem=True),
        world.call("POST", f"/bank/transfers/{h1.transfer}/cancel", "parent2", idem=True),
    ]  # fmt: skip
    for reply in attacks:
        refused(reply, *h1.secrets)
    assert world.call("GET", f"/payments/{pid}").json()["state"] == h1.payment["state"], (
        "nothing changed"
    )
    names = [r["display_name"] for r in world.call("GET", "/recipients").json()["items"]]
    assert "Hacked" not in names


def test_lists_never_mix_households(world: World) -> None:
    h1 = Records(world)
    seen = ""
    for who in ("parent2", "student2"):
        for path in ("/payments", "/recipients", "/documents", "/escrows", "/quotes", "/bank/accounts",
                     "/bank/transfers", "/audit/events?limit=100"):  # fmt: skip
            reply = world.call("GET", path, who)
            if reply.status_code == 200:
                seen += reply.text
    for text in [*h1.secrets, *h1.ids, "usr_demo_parent"]:
        assert text not in seen, text


def test_an_mfa_proof_cannot_be_borrowed_or_minted_for_someone_elses_record(world: World) -> None:
    h1 = Records(world)
    stolen = world.mfa("parent", "confirm_escrow", h1.escrow)
    borrowed = world.call("POST", f"/escrows/{h1.escrow}/confirm", "parent2", idem=True, mfa=stolen)
    assert borrowed.status_code in (403, 404)
    mint = world.client.post(
        "/api/v1/auth/mfa/verify", headers=world.login("parent2"),
        json={"code": "246810", "scope": "confirm_escrow", "subject_id": h1.escrow},
    )  # fmt: skip
    assert mint.status_code == 404, "another household's escrow does not even exist for you"
    assert world.call("GET", f"/escrows/{h1.escrow}").json()["status"] == "PENDING_CONFIRMATION"


def test_idempotency_keys_belong_to_the_caller(world: World) -> None:
    """Reusing another family's Idempotency-Key must never replay their stored response."""
    h1 = Records(world)
    key = str(uuid.uuid4())
    first = (world.clock.now() + timedelta(days=3)).date().isoformat()

    def plan(who: str, recipient_id: str, reference: str) -> Any:
        return world.call("POST", "/escrows", who, idem=key, json={
            "recipient_id": recipient_id, "purpose": "TUITION",
            "total": {"amount_minor": 500_000, "currency": "GBP"}, "tranches": 1,
            "first_release": first, "cadence": "ONCE", "reference": reference,
        })  # fmt: skip

    mine = plan("parent", h1.recipient, "H1-KEYED")
    their_recipient = world.call("GET", "/recipients", "parent2").json()["items"][0]["recipient_id"]
    theirs = plan("parent2", their_recipient, "H2-KEYED")
    assert mine.status_code == 201 and theirs.status_code == 201
    assert theirs.json()["escrow_id"] != mine.json()["escrow_id"]
    assert "H1-KEYED" not in theirs.text and h1.secrets[0] not in theirs.text
    assert theirs.headers.get("Idempotent-Replay") is None


def test_a_student_cannot_do_a_parents_job_even_in_their_own_household(world: World) -> None:
    h1 = Records(world)
    pid = h1.payment["payment_id"]
    for reply in (
        world.call("POST", f"/payments/{pid}/approve", "student", idem=True, json={"confirm_summary_hash": "x" * 64}),
        world.call("POST", f"/escrows/{h1.escrow}/confirm", "student", idem=True),
        world.call("POST", f"/bank/transfers/{h1.transfer}/confirm", "student", idem=True),
        world.call("PATCH", f"/recipients/{h1.recipient}", "student", json={"allowlisted": True}),
        world.call("POST", "/me/reset", "student"),
    ):  # fmt: skip
        refused(reply)
    assert world.call("GET", f"/payments/{pid}", "student").status_code == 200, "students may look"
