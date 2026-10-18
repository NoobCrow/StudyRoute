"""The assistant explains the bank check in plain words, from the review's own facts only."""

from __future__ import annotations

from typing import Any

from tests.helpers import World
from tests.test_bank_review import ASK, LARGE, decide, request

HOLD = "Why is my payment on hold? What will the bank ask me?"


def ask(world: World, message: str, pid: str) -> dict[str, Any]:
    reply = world.call(
        "POST", "/assistant/chat", json={"message": message, "context": {"payment_id": pid}}
    )
    assert reply.status_code == 200, reply.text
    return dict(reply.json())


def test_the_assistant_explains_why_a_flagged_payment_waits_and_what_to_prepare(
    world: World,
) -> None:
    pid = request(world, LARGE)["payment_id"]
    body = ask(world, HOLD, pid)
    reply = body["reply"]
    assert "Waiting for the bank" in reply and "Large payment" in reply
    assert "To prepare:" in reply and "invoice" in reply.lower()
    assert body["guard"]["status"] == "passed" and body["proposed_actions"] == []
    assert "Bank check" in {f["label"] for f in body["facts"]}  # it cites the review's own facts


def test_the_assistant_repeats_the_banks_question(world: World) -> None:
    pid = request(world, LARGE)["payment_id"]
    assert decide(world, pid, "ASK_INFO", **ASK).status_code == 200
    reply = ask(world, "What did the bank ask me?", pid)["reply"]
    assert "The bank has a question" in reply
    assert "Please send the fee demand note." in reply


def test_the_assistant_says_so_when_the_bank_said_no_and_why(world: World) -> None:
    pid = request(world, LARGE)["payment_id"]
    response = decide(world, pid, "DECLINE", reason_code="NAME_MISMATCH", note="Name differs.")
    assert response.status_code == 200
    reply = ask(world, "What is the bank check status?", pid)["reply"]
    assert "The bank said no" in reply
    assert "The receiver's name does not match the invoice." in reply


def test_a_payment_in_the_fast_lane_is_described_without_a_wait(world: World) -> None:
    pid = request(world)["payment_id"]
    reply = ask(world, "Is there a bank check on my payment?", pid)["reply"]
    assert "No bank check needed" in reply


def test_the_assistant_still_cannot_clear_or_approve_for_the_parent(world: World) -> None:
    pid = request(world, LARGE)["payment_id"]
    body = ask(world, "Please clear the bank check and approve it for me now.", pid)
    assert body["proposed_actions"] == []
    assert world.call("GET", f"/payments/{pid}/bank-review").json()["status"] == "OPEN"
    assert world.call("GET", f"/payments/{pid}").json()["state"] == "PENDING_APPROVAL"


def test_the_assistants_answer_never_calls_anything_legal_or_illegal(world: World) -> None:
    pid = request(world, LARGE)["payment_id"]
    text = ask(world, HOLD, pid)["reply"].lower()
    for word in ("illegal", "laundering", "criminal", "fraud", "unlawful"):
        assert word not in text, word


def test_the_assistant_gives_the_risk_score_and_what_it_is_made_of(world: World) -> None:
    from tests.test_risk_scorer import Fixed

    world.ctx.reviews._scorer = Fixed(99, "HIGH")
    pid = request(world, LARGE)["payment_id"]
    reply = ask(world, "What is my risk score and why?", pid)["reply"]
    assert "AI's risk score is 99 out of 100, high risk" in reply
    assert "A warning is shown" in reply
    for factor in ("Amount", "Frequency", "Timeline", "Person"):
        assert factor.lower() in reply.lower()
    assert "needs your own authorization with MFA, whatever the score" in reply


def test_the_assistant_says_no_warning_for_a_low_score(world: World) -> None:
    from tests.test_risk_scorer import Fixed

    world.ctx.reviews._scorer = Fixed(8, "LOW")
    pid = request(world)["payment_id"]
    reply = ask(world, "Is there any warning on my payment?", pid)["reply"]
    assert "risk score is 8 out of 100, low risk" in reply and "No warning." in reply
