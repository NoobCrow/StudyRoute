"""GET /payments/{id}/compliance-report: a regulator-style evidence pack for one payment."""

from __future__ import annotations

from typing import Any

from app.core.crypto import hash_object
from tests.helpers import UNIVERSITY, World

IBAN_TAIL = "4821"
FULL_IBAN = "GB08EXMP12345612344821"


def settled(world: World, recipient: str = UNIVERSITY) -> str:
    world.verify_kyc()
    rid = world.recipient_id(recipient)
    world.allowlist(rid)
    payment = world.draft(recipient_id=rid)
    pid = str(payment["payment_id"])
    approval = world.call("POST", f"/payments/{pid}/request-approval", idem=True).json()
    assert world.approve(approval).status_code == 200
    world.clock.advance(3)
    world.ctx.worker.tick()
    world.clock.advance(5)
    world.ctx.worker.tick()
    assert world.call("GET", f"/payments/{pid}").json()["state"] in {"SETTLED", "FAILED"}
    return pid


def report(world: World, pid: str, who: str | None = "parent") -> Any:
    return world.call("GET", f"/payments/{pid}/compliance-report", who)


def controls(body: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {c["key"]: c for c in body["controls"]}


def test_a_settled_payment_passes_every_control_with_evidence(world: World) -> None:
    pid = settled(world)
    response = report(world, pid)
    assert response.status_code == 200
    body = response.json()
    assert body["report_type"] == "payment_compliance_report"
    assert body["payment"]["state"] == "SETTLED" and body["payment"]["uetr"]
    got = controls(body)
    assert list(got) == [
        "kyc", "allowlist", "sanctions", "caps", "mfa", "summary_hash", "human_approval",
        "travel_rule", "provider_confirmation", "audit_chain",
    ]  # fmt: skip
    assert {c["result"] for c in got.values()} == {"PASS"}, got
    assert got["mfa"]["evidence"].startswith("Proof mfa:")
    assert body["approval"]["summary_hash"].startswith("sha256:")
    assert body["approval"]["approved_by"] == world.ids["parent"]


def test_the_travel_rule_parties_are_present_and_the_account_is_masked(world: World) -> None:
    body = report(world, settled(world)).json()
    originator, beneficiary = body["parties"]["originator"], body["parties"]["beneficiary"]
    assert originator["name"] == "Demo Parent" and originator["country"] == "BD"
    assert beneficiary["name"] == UNIVERSITY and beneficiary["bic"] == "EXMPGB2L"
    assert beneficiary["account_masked"].endswith(IBAN_TAIL)
    assert FULL_IBAN not in report(world, settled_id(world)).text


def settled_id(world: World) -> str:
    return str(world.call("GET", "/payments").json()["items"][0]["payment_id"])


def test_the_audit_excerpt_covers_the_whole_life_of_the_payment(world: World) -> None:
    body = report(world, settled(world)).json()
    actions = [e["action"] for e in body["audit"]["events"]]
    for expected in (
        "payment.created",
        "approval.requested",
        "approval.granted",
        "webhook.accepted",
    ):
        assert expected in actions, expected
    seqs = [e["seq"] for e in body["audit"]["events"]]
    assert seqs == sorted(seqs)
    assert body["audit"]["chain"]["status"] == "PASS"
    assert body["audit"]["chain"]["head"]["hash"]
    assert all(e["this_event_hash"] and e["prev_event_hash"] for e in body["audit"]["events"])


def test_the_report_hash_lets_anyone_detect_a_changed_report(world: World) -> None:
    body = report(world, settled(world)).json()
    claimed = body.pop("report_hash")
    assert claimed == hash_object(body)
    body["amount"]["parent_pays"] = "BDT 1.00"
    assert claimed != hash_object(body)


def test_a_payment_that_is_still_a_draft_shows_what_is_missing_honestly(world: World) -> None:
    draft = world.draft()
    got = controls(report(world, draft["payment_id"]).json())
    assert got["kyc"]["result"] == "PENDING"
    assert got["allowlist"]["result"] == "PENDING"
    assert got["mfa"]["result"] == "NOT_YET" and got["human_approval"]["result"] == "NOT_YET"
    assert got["provider_confirmation"]["result"] == "NOT_YET"
    assert got["sanctions"]["result"] == "PASS" and got["travel_rule"]["result"] == "PASS"


def test_a_failed_payment_still_reports_the_providers_signed_answer(world: World) -> None:
    pid = settled(world, "FAIL_TEST University (synthetic)")
    body = report(world, pid).json()
    assert body["payment"]["state"] == "FAILED"
    assert controls(body)["provider_confirmation"]["result"] == "PASS"
    assert body["payment"]["failure_reason"]


def test_the_report_states_that_it_is_synthetic_and_indicative(world: World) -> None:
    body = report(world, settled(world)).json()
    assert body["synthetic"] is True
    assert "Indicative. Confirm with your AD bank." in body["disclaimer"]
    assert "not a legal limit" in controls(body)["caps"]["evidence"]
    assert controls(body)["caps"]["label"].startswith("Sandbox cap")


def test_who_may_read_the_report(world: World) -> None:
    pid = settled(world)
    assert report(world, pid, "parent").status_code == 200
    assert report(world, pid, "admin").status_code == 200
    assert report(world, pid, "student").status_code == 403, "students have no audit access"
    assert report(world, pid, None).status_code == 401
    ai = world.client.get(f"/api/v1/payments/{pid}/compliance-report", headers=world.ai_headers())
    assert ai.status_code == 403
    assert report(world, "pay_does_not_exist").status_code == 404


def test_no_secret_or_token_is_in_the_report(world: World) -> None:
    text = report(world, settled(world)).text
    for marker in ("eyJ", "Bearer ", "BEGIN", "refresh_token", "Sandbox#2026", "246810"):
        assert marker not in text, marker
    for secret in world.ctx.secrets.webhook_secrets("prov_b"):
        assert secret not in text


def test_reading_the_report_changes_nothing(world: World) -> None:
    pid = settled(world)
    before = len(world.audit_rows())
    report(world, pid)
    report(world, pid)
    assert len(world.audit_rows()) == before
