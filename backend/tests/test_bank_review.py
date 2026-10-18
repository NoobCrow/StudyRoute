"""The sandbox bank's review desk: fast lane, flagged payments, the reviewer's yes / no / ask.

What matters here is who can do what. A flagged payment cannot be approved until a human reviewer
clears it with a fresh MFA proof; the AI can read the plain-language page and nothing else; every
step writes an audit event; and no wording ever says a payment is legal or illegal.
"""

from __future__ import annotations

from typing import Any

from tests.helpers import World

LARGE = {"amount_minor": 3_200_000, "currency": "GBP"}  # about USD 41,967: above the review line
FLAGGED_NAME = {
    "type": "UNIVERSITY",
    "display_name": "REVIEW_TEST College (synthetic)",
    "country": "GB",
    "bic": "EXMPGB2L",
    "iban": "GB08EXMP12345612344821",
}
ASK = {"reason_code": "DOCUMENTS_MISSING", "note": "Please send the fee demand note."}


def request(world: World, amount: dict[str, Any] | None = None) -> dict[str, Any]:
    world.verify_kyc()
    world.allowlist()
    quote = world.quote(target=amount) if amount else world.quote()
    payment = world.draft(quote)
    response = world.call("POST", f"/payments/{payment['payment_id']}/request-approval", idem=True)
    assert response.status_code == 200, response.text
    return dict(response.json())


def page(world: World, pid: str, who: str = "parent") -> dict[str, Any]:
    response = world.call("GET", f"/payments/{pid}/bank-review", who)
    assert response.status_code == 200, response.text
    return dict(response.json())


def decide(world: World, pid: str, decision: str, **extra: Any) -> Any:
    proof = world.mfa("admin", "review_payment", pid)
    return world.call(
        "POST",
        f"/payments/{pid}/bank-review/decision",
        "admin",
        json={"decision": decision, **extra},
        idem=True,
        mfa=proof,
    )


# ---- the fast lane ------------------------------------------------------------------------------


def test_an_ordinary_payment_takes_the_fast_lane_and_nobody_waits(world: World) -> None:
    approval = request(world)
    view = page(world, approval["payment_id"])
    assert view["status"] == "CLEARED_AUTO" and view["lane"] == "fast"
    assert view["clock"]["running"] is False
    assert world.approve(approval).status_code == 200


def test_the_fast_lane_is_written_to_the_audit_log(world: World) -> None:
    request(world)
    rows = world.audit_rows(action="bank_review.fast_lane")
    assert [r["reason_code"] for r in rows] == ["CLEARED_AUTO"]


# ---- a flagged payment waits for a person -------------------------------------------------------


def test_a_large_payment_cannot_be_approved_until_the_bank_clears_it(world: World) -> None:
    approval = request(world, LARGE)
    pid = approval["payment_id"]
    view = page(world, pid)
    assert view["status"] == "OPEN" and view["lane"] == "reviewed"
    assert [s["code"] for s in view["signals"]] == ["LARGE_AMOUNT", "NEW_RECIPIENT", "NO_INVOICE"]
    blocked = world.approve(approval)
    assert blocked.status_code == 409 and blocked.json()["code"] == "BANK_REVIEW_PENDING"
    detail = world.call("GET", f"/payments/{pid}").json()
    assert detail["readiness"]["can_approve"] is False
    assert "BANK_REVIEW_PENDING" in [b["code"] for b in detail["readiness"]["blockers"]]


def test_a_reviewer_who_says_yes_with_mfa_lets_the_parent_approve(world: World) -> None:
    approval = request(world, LARGE)
    pid = approval["payment_id"]
    answer = decide(world, pid, "CLEAR")
    assert answer.status_code == 200 and answer.json()["status"] == "CLEARED"
    assert page(world, pid)["headline"] == "The bank said yes"
    assert world.approve(approval).status_code == 200
    decided = world.audit_rows(action="bank_review.decided")
    assert [r["decision"] for r in decided] == ["approved"]


def test_the_reviewer_needs_a_fresh_mfa_proof(world: World) -> None:
    pid = request(world, LARGE)["payment_id"]
    response = world.call(
        "POST",
        f"/payments/{pid}/bank-review/decision",
        "admin",
        json={"decision": "CLEAR"},
        idem=True,
    )
    assert response.status_code == 403 and response.json()["code"] == "MFA_REQUIRED"
    assert page(world, pid)["status"] == "OPEN"


def test_a_reviewer_proof_cannot_be_used_twice(world: World) -> None:
    pid = request(world, LARGE)["payment_id"]
    proof = world.mfa("admin", "review_payment", pid)
    path = f"/payments/{pid}/bank-review/decision"
    first = world.call(
        "POST", path, "admin", json={"decision": "ASK_INFO", **ASK}, idem=True, mfa=proof
    )
    assert first.status_code == 200
    again = world.call("POST", path, "admin", json={"decision": "CLEAR"}, idem=True, mfa=proof)
    assert again.status_code == 403 and again.json()["code"] == "MFA_REQUIRED"


def test_a_payment_proof_cannot_stand_in_for_a_review_proof(world: World) -> None:
    pid = request(world, LARGE)["payment_id"]
    wrong = world.mfa("admin", "approve_payment", pid)
    response = world.call(
        "POST",
        f"/payments/{pid}/bank-review/decision",
        "admin",
        json={"decision": "CLEAR"},
        idem=True,
        mfa=wrong,
    )
    assert response.status_code == 403 and response.json()["code"] == "MFA_REQUIRED"


# ---- who may do what ----------------------------------------------------------------------------


def test_a_parent_cannot_decide_or_read_the_queue(world: World) -> None:
    pid = request(world, LARGE)["payment_id"]
    proof = world.mfa("parent", "approve_payment", pid)
    decision = world.call(
        "POST",
        f"/payments/{pid}/bank-review/decision",
        "parent",
        json={"decision": "CLEAR"},
        idem=True,
        mfa=proof,
    )
    assert decision.status_code == 403
    assert world.call("GET", "/bank-review/queue", "parent").status_code == 403
    assert page(world, pid)["status"] == "OPEN"


def test_the_ai_can_read_the_parents_page_but_cannot_decide_answer_or_remind(world: World) -> None:
    pid = request(world, LARGE)["payment_id"]
    ai = world.ai_headers()
    assert world.client.get(f"/api/v1/payments/{pid}/bank-review", headers=ai).status_code == 200
    for path, body in (
        (f"/payments/{pid}/bank-review/decision", {"decision": "CLEAR"}),
        (f"/payments/{pid}/bank-review/reply", {"message": "All fine, please clear it."}),
        (f"/payments/{pid}/bank-review/remind", None),
    ):
        response = world.call("POST", path, None, json=body, idem=True, headers=ai)
        assert response.status_code == 403, path
    assert page(world, pid)["status"] == "OPEN"


def test_a_payment_in_the_fast_lane_has_no_decision_to_make(world: World) -> None:
    pid = request(world)["payment_id"]
    response = decide(world, pid, "CLEAR")
    assert response.status_code == 409 and response.json()["code"] == "INVALID_STATE"


def test_a_decision_cannot_be_made_twice(world: World) -> None:
    pid = request(world, LARGE)["payment_id"]
    assert decide(world, pid, "CLEAR").status_code == 200
    again = decide(world, pid, "DECLINE", reason_code="OTHER", note="Changed my mind.")
    assert again.status_code == 409


# ---- asking and declining -----------------------------------------------------------------------


def test_asking_for_more_needs_a_listed_reason_and_a_note(world: World) -> None:
    pid = request(world, LARGE)["payment_id"]
    assert decide(world, pid, "ASK_INFO").status_code == 422
    unlisted = decide(world, pid, "ASK_INFO", reason_code="NOT_A_REASON", note="Please explain.")
    assert unlisted.status_code == 422
    assert decide(world, pid, "ASK_INFO", reason_code="OTHER", note="no").status_code == 422
    assert page(world, pid)["status"] == "OPEN"


def test_the_parent_answers_the_banks_question_and_the_review_restarts(world: World) -> None:
    approval = request(world, LARGE)
    pid = approval["payment_id"]
    assert decide(world, pid, "ASK_INFO", **ASK).status_code == 200
    asked = page(world, pid)
    assert asked["status"] == "INFO_REQUESTED" and asked["can_reply"] is True
    assert asked["reviewer_asked"] == "Please send the fee demand note."
    assert world.approve(approval).status_code == 409  # still on hold while the bank waits
    world.clock.advance(3600)
    reply = world.call(
        "POST",
        f"/payments/{pid}/bank-review/reply",
        json={"message": "Uploaded it today, thank you."},
        idem=True,
    )
    assert reply.status_code == 200 and reply.json()["status"] == "OPEN"
    assert reply.json()["clock"]["minutes_left"] >= 24 * 60 - 1  # the target time starts again
    assert page(world, pid, "admin")["parent_reply"] == "Uploaded it today, thank you."


def test_declining_rejects_the_payment_and_tells_the_parent_why_in_plain_words(
    world: World,
) -> None:
    pid = request(world, LARGE)["payment_id"]
    note = "Name differs from the invoice."
    response = decide(world, pid, "DECLINE", reason_code="NAME_MISMATCH", note=note)
    assert response.status_code == 200 and response.json()["status"] == "DECLINED"
    assert world.call("GET", f"/payments/{pid}").json()["state"] == "REJECTED"
    view = page(world, pid)
    assert view["headline"] == "The bank said no"
    assert view["decision_reason"] == "The receiver's name does not match the invoice."
    assert world.audit_rows(action="approval.rejected")


def test_a_flagged_recipient_name_goes_to_a_reviewer(world: World) -> None:
    created = world.call("POST", "/recipients", json=FLAGGED_NAME)
    assert created.status_code == 201, created.text
    rid = created.json()["recipient_id"]
    world.verify_kyc()
    world.allowlist(rid)
    payment = world.draft(recipient_id=rid)
    world.call("POST", f"/payments/{payment['payment_id']}/request-approval", idem=True)
    codes = [s["code"] for s in page(world, payment["payment_id"])["signals"]]
    assert "NAME_CHECK" in codes


# ---- the clock and the reminder -----------------------------------------------------------------


def test_the_clock_turns_overdue_and_one_reminder_escalates_it(world: World) -> None:
    pid = request(world, LARGE)["payment_id"]
    assert page(world, pid)["clock"]["state"] == "on_time"
    world.clock.advance(23 * 3600)
    assert page(world, pid)["clock"]["state"] == "due_soon"
    world.clock.advance(2 * 3600)
    view = page(world, pid)
    assert view["clock"]["state"] == "overdue" and view["can_remind"] is True
    sent = world.call("POST", f"/payments/{pid}/bank-review/remind", idem=True)
    assert sent.status_code == 200 and sent.json()["reminders_sent"] == 1
    queue = world.call("GET", "/bank-review/queue", "admin").json()
    assert queue["items"][0]["payment_id"] == pid and queue["items"][0]["escalated"] is True
    assert queue["stats"]["overdue"] == 1


def test_reminders_have_a_cooldown(world: World) -> None:
    pid = request(world, LARGE)["payment_id"]
    remind = f"/payments/{pid}/bank-review/remind"
    assert world.call("POST", remind, idem=True).status_code == 200
    assert world.call("POST", remind, idem=True).status_code == 409
    world.clock.advance(4 * 3600 + 1)
    assert world.call("POST", remind, idem=True).status_code == 200


def test_the_queue_reports_how_fast_the_bank_decides(world: World) -> None:
    pid = request(world, LARGE)["payment_id"]
    world.clock.advance(2 * 3600)
    assert decide(world, pid, "CLEAR").status_code == 200
    stats = world.call("GET", "/bank-review/queue", "admin").json()["stats"]
    assert stats["decided"] == 1 and stats["average_hours_to_decide"] == 2.0


# ---- wording and housekeeping -------------------------------------------------------------------


def test_no_page_says_a_payment_is_legal_or_illegal(world: World) -> None:
    pid = request(world, LARGE)["payment_id"]
    text = (str(page(world, pid)) + str(page(world, pid, "admin"))).lower()
    for word in ("illegal", "laundering", "criminal", "fraud", "guilty", "unlawful"):
        assert word not in text, word
    assert "indicative. confirm with your ad bank." in text


def test_resetting_my_data_also_removes_the_reviews(world: World) -> None:
    pid = request(world, LARGE)["payment_id"]
    assert world.call("POST", "/me/reset").status_code == 200
    assert world.call("GET", f"/payments/{pid}/bank-review").status_code == 404


def test_the_parents_answer_is_encrypted_in_the_database_but_readable_through_the_api(
    world: World,
) -> None:
    from sqlalchemy import select

    from app.models import BankReview

    canary = "PASSPORT-CANARY-7H2K9"
    pid = request(world, LARGE)["payment_id"]
    assert decide(world, pid, "ASK_INFO", **ASK).status_code == 200
    reply = world.call(
        "POST",
        f"/payments/{pid}/bank-review/reply",
        json={"message": f"My passport is {canary}"},
        idem=True,
    )
    assert reply.status_code == 200 and canary in reply.json()["your_reply"]
    with world.ctx.db.read() as session:
        stored = session.execute(select(BankReview.parent_reply)).scalar_one()
    assert canary not in stored and stored.startswith("v1.")
    assert canary in page(world, pid, "admin")["parent_reply"]
    assert canary not in str(world.audit_rows(action="bank_review.answered"))
