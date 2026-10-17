"""Synthetic institution-policy regressions; no account identity or bank validation."""

from __future__ import annotations

import pytest
from sqlalchemy import select, text

from app.domain.institution_routes import MMU_ID, SOURCE
from app.models import Payment, RecipientInstitution


def create_recipient(world, **changes):
    body = {
        "type": "UNIVERSITY",
        "display_name": "Synthetic University",
        "country": "GB",
        "bic": "WESTGB2L",
        "iban": "GB82WEST12345698765432",
    }
    body.update(changes)
    return world.call("POST", "/recipients", json=body)


def rename(world, rid, name):
    proof = world.mfa("parent", "allowlist_recipient", rid)
    return world.call("PATCH", f"/recipients/{rid}", json={"display_name": name}, mfa=proof)


def test_catalog_requires_auth_and_labels_unknown(world):
    assert world.call("GET", "/institutions", who=None).status_code == 401
    result = world.call("GET", "/institutions").json()
    assert result["items"][0]["source_url"] == SOURCE
    assert result["unknown_status"] == "UNVERIFIED"
    rid = world.recipient_id()
    policy = world.call("GET", f"/recipients/{rid}/route-policy").json()
    assert policy["status"] == "UNVERIFIED"
    assert policy["identity_verified"] is False


@pytest.mark.parametrize(
    "changes",
    [
        {"institution_id": MMU_ID},
        {"display_name": "Manchester Metropolitan University (synthetic)"},
        {"display_name": "MANCHESTER  METROPOLITAN UNIVERSITY fee office"},
    ],
)
def test_known_policy_blocks_quote_and_audits_without_inserting(world, changes):
    reply = create_recipient(world, **changes)
    assert reply.status_code == 201, reply.text
    rid = reply.json()["recipient_id"]
    body = {
        "target": {"amount_minor": 1000000, "currency": "GBP"},
        "purpose": "TUITION",
        "destination_country": "GB",
        "charge_code": "OUR",
        "recipient_id": rid,
    }
    response = world.call("POST", "/quotes", json=body)
    assert response.status_code == 422, response.text
    assert response.json()["code"] == "ROUTE_NOT_SUPPORTED"
    assert SOURCE in response.json()["detail"]
    assert world.call("GET", "/quotes").json()["items"] == []
    assert world.audit_rows(action="institution.route_blocked", recipient_id=rid)


def test_unbound_quote_cannot_bypass_draft_guard(world):
    rid = create_recipient(world, institution_id=MMU_ID).json()["recipient_id"]
    quote = world.quote()
    reply = world.call(
        "POST",
        "/payments",
        idem=True,
        json={
            "quote_id": quote["quote_id"],
            "provider_id": "prov_b",
            "recipient_id": rid,
            "reference": "SYNTHETIC POLICY TEST",
        },
    )
    assert reply.status_code == 422, reply.text
    with world.ctx.db.read() as session:
        assert list(session.scalars(select(Payment))) == []


def test_renaming_cannot_clear_binding_and_patch_cannot_override(world):
    rid = create_recipient(world, institution_id=MMU_ID).json()["recipient_id"]
    assert rename(world, rid, "Ordinary Synthetic University").status_code == 200
    policy = world.call("GET", f"/recipients/{rid}/route-policy").json()
    assert policy["status"] == "DIRECT_BANK_TUITION_BLOCKED"
    assert (
        world.call("PATCH", f"/recipients/{rid}", json={"institution_id": None}).status_code == 422
    )


def test_legacy_recognized_name_is_bound_before_rename(world):
    rid = create_recipient(world, display_name="Manchester Metropolitan University").json()[
        "recipient_id"
    ]
    with world.ctx.db.write() as session:
        session.delete(session.get(RecipientInstitution, rid))
    assert rename(world, rid, "Renamed University").status_code == 200
    assert (
        world.call("GET", f"/recipients/{rid}/route-policy").json()["policy"]["institution_id"]
        == MMU_ID
    )


@pytest.mark.parametrize(
    "changes",
    [
        {"institution_id": "imaginary-policy"},
        {"institution_id": MMU_ID, "type": "STUDENT"},
        {"institution_id": MMU_ID, "country": "US"},
    ],
)
def test_invalid_declarations_rejected(world, changes):
    reply = create_recipient(world, **changes)
    assert reply.status_code == 422, reply.text


def test_university_of_manchester_is_not_mmu_and_living_is_out_of_scope(world):
    rid = create_recipient(world, display_name="The University of Manchester").json()[
        "recipient_id"
    ]
    assert world.quote(recipient_id=rid)["recipient_id"] == rid
    mmu = create_recipient(world, institution_id=MMU_ID).json()["recipient_id"]
    assert world.quote(recipient_id=mmu, purpose="LIVING")["purpose"] == "LIVING"


def test_existing_payment_blocker_and_request_approval(world):
    world.verify_kyc()
    world.allowlist()
    draft = world.draft()
    rid = world.recipient_id()
    # A newly reviewed/declared institution binding also protects pre-existing drafts.
    with world.ctx.db.write() as session:
        session.add(
            RecipientInstitution(
                recipient_id=rid, institution_id=MMU_ID, bound_at=world.clock.now()
            )
        )
    pid = draft["payment_id"]
    reply = world.call("POST", f"/payments/{pid}/request-approval", idem=True)
    assert reply.status_code == 422, reply.text
    with world.ctx.db.read() as session:
        payment = session.get(Payment, pid)
        assert payment.state == "QUOTED"
        from app.domain.rules import load_rules

        codes = [
            item["code"]
            for item in world.ctx.payments.blockers(session, load_rules(session), payment)
        ]
        assert "INSTITUTION_ROUTE_UNSUPPORTED" in codes


def test_existing_payment_cannot_be_approved_after_binding(world):
    approval = world.ready_payment()
    with world.ctx.db.write() as session:
        session.add(
            RecipientInstitution(
                recipient_id=world.recipient_id(), institution_id=MMU_ID, bound_at=world.clock.now()
            )
        )
    reply = world.approve(approval)
    assert reply.status_code == 422, reply.text


def test_system_submit_rechecks_policy(world):
    approval = world.ready_payment()
    assert world.approve(approval).status_code == 200
    rid = world.recipient_id()
    from app.core.errors import RouteNotSupported
    from app.domain.rules import load_rules

    with world.ctx.db.write() as session:
        session.add(
            RecipientInstitution(
                recipient_id=rid, institution_id=MMU_ID, bound_at=world.clock.now()
            )
        )
    with pytest.raises(RouteNotSupported), world.ctx.db.write() as session:
        world.ctx.payments.submit(session, load_rules(session), approval["payment_id"])


def test_new_table_is_additive_without_resetting_existing_database(world):
    before = world.recipient_id()
    with world.ctx.db.write() as session:
        session.execute(text("DROP TABLE recipient_institutions"))
    world.ctx.db.create_schema()
    assert world.recipient_id() == before
    assert create_recipient(world, institution_id=MMU_ID).status_code == 201


def test_household_reset_deletes_binding_without_foreign_key_failure(world):
    create_recipient(world, institution_id=MMU_ID)
    # Domain-level reset avoids assuming the route name and tests the FK lifecycle directly.
    from app.domain.auth import human_actor
    from app.domain.privacy import reset_household_data
    from app.models import User

    with world.ctx.db.write() as session:
        actor = human_actor(session.get(User, world.ids["parent"]))
        reset_household_data(session, world.ctx.audit, actor)
    with world.ctx.db.read() as session:
        assert list(session.scalars(select(RecipientInstitution))) == []
