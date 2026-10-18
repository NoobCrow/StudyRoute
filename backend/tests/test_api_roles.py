"""Human roles and object ownership (T10, T11)."""

from __future__ import annotations

from app.domain.auth import create_user
from app.domain.constants import ActorKind
from tests.helpers import PASSWORD, World

OTHER_EMAIL = "other.parent@demo.studyroute.test"


def other_parent_headers(world: World) -> dict[str, str]:
    with world.ctx.db.write() as session:
        create_user(
            session,
            passwords=world.ctx.passwords,
            cipher=world.ctx.cipher,
            now=world.clock.now(),
            email=OTHER_EMAIL,
            display_name="Other Parent",
            role=ActorKind.PARENT,
            password=PASSWORD,
            kyc_status="VERIFIED",
        )
    login = {"email": OTHER_EMAIL, "password": PASSWORD}
    response = world.client.post("/api/v1/auth/login", json=login)
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def test_T10_a_student_cannot_approve_and_gets_403_forbidden(world: World) -> None:
    approval = world.ready_payment()
    pid = approval["payment_id"]
    response = world.call(
        "POST",
        f"/payments/{pid}/approve",
        "student",
        json={"confirm_summary_hash": approval["summary_hash"]},
        idem=True,
    )
    assert response.status_code == 403
    assert response.json()["code"] == "FORBIDDEN"


def test_students_can_quote_and_view_but_not_draft_allowlist_or_cancel(world: World) -> None:
    approval = world.ready_payment()
    pid = approval["payment_id"]
    assert world.quote(who="student")["quote_id"]
    assert world.call("GET", f"/payments/{pid}", "student").status_code == 200
    assert world.call("GET", f"/payments/{pid}/tracker", "student").status_code == 200
    assert world.call("POST", f"/payments/{pid}/cancel", "student", idem=True).status_code == 403
    rid = world.recipient_id()
    patch = world.call("PATCH", f"/recipients/{rid}", "student", json={"allowlisted": True})
    assert patch.status_code == 403
    body = {
        "quote_id": approval["summary"]["quote_id"],
        "provider_id": "prov_b",
        "recipient_id": rid,
        "reference": "X",
    }
    assert world.call("POST", "/payments", "student", json=body, idem=True).status_code == 403


def test_a_student_can_add_recipient_details_for_the_parent(world: World) -> None:
    created = world.call(
        "POST",
        "/recipients",
        "student",
        json={
            "type": "STUDENT",
            "display_name": "Demo Student",
            "country": "DE",
            "bic": "EXMPDEFF",
            "iban": "DE54370400440532013048",
        },
    )
    assert created.status_code == 201
    names = [r["display_name"] for r in world.call("GET", "/recipients").json()["items"]]
    assert "Demo Student" in names


def test_admin_cannot_approve_create_drafts_or_quotes(world: World) -> None:
    approval = world.ready_payment()
    pid = approval["payment_id"]
    body = {"confirm_summary_hash": approval["summary_hash"]}
    approve = world.call("POST", f"/payments/{pid}/approve", "admin", json=body, idem=True)
    assert approve.status_code == 403
    quote = {"target": {"amount_minor": 1000, "currency": "GBP"}, "destination_country": "GB"}
    assert world.call("POST", "/quotes", "admin", json=quote).status_code == 403


def test_T11_another_users_payment_is_404_not_403(world: World) -> None:
    approval = world.ready_payment()
    pid = approval["payment_id"]
    outsider = other_parent_headers(world)
    for path in (
        f"/payments/{pid}",
        f"/payments/{pid}/tracker",
        f"/payments/{pid}/instruction-preview",
    ):
        assert world.client.get(f"/api/v1{path}", headers=outsider).status_code == 404
    approve = world.client.post(
        f"/api/v1/payments/{pid}/approve",
        headers={**outsider, "Idempotency-Key": "aaaaaaaa-bbbb-4ccc-8ddd-eeeeeeeeeeee"},
        json={"confirm_summary_hash": approval["summary_hash"]},
    )
    assert approve.status_code == 404
    assert approve.json()["code"] == "NOT_FOUND"
    unknown = world.client.get("/api/v1/payments/pay_does_not_exist", headers=outsider)
    owned_by_other = world.client.get(f"/api/v1/payments/{pid}", headers=outsider)
    assert unknown.json()["detail"] == owned_by_other.json()["detail"]


def test_listings_never_include_another_users_data(world: World) -> None:
    world.ready_payment()
    outsider = other_parent_headers(world)
    for path in ("/payments", "/recipients", "/quotes", "/documents"):
        assert world.client.get(f"/api/v1{path}", headers=outsider).json()["items"] == [], path
    qid = world.quote()["quote_id"]
    assert world.client.get(f"/api/v1/quotes/{qid}", headers=outsider).status_code == 404
