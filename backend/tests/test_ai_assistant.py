"""The assistant in TEMPLATE MODE (no API key): explanations from engine facts only."""

from __future__ import annotations

from typing import Any

from app.ai.number_guard import numbers_in
from tests.helpers import World


def ask(world: World, message: str, who: str = "parent", **context: Any):
    return world.call("POST", "/assistant/chat", who, json={"message": message, "context": context})


def facts_numbers(body: dict[str, Any]) -> set:
    prompt = body["debug"]["masked_prompt"]
    values = [line.split(" | ", 2)[2] for line in prompt.splitlines() if line.startswith("fact_")]
    return {n for v in values for n in numbers_in(v)}


def test_health_reports_template_mode_without_a_key(world: World) -> None:
    body = world.client.get("/health").json()
    assert body["ai_mode"] == "template"


def test_why_is_b_cheaper_than_a_cites_engine_numbers_and_lists_facts_used(world: World) -> None:
    quote = world.quote()
    response = ask(world, "Why is Provider B cheaper than A?", quote_id=quote["quote_id"])
    assert response.status_code == 200
    body = response.json()
    reply = body["reply"]
    assert "1.58%" in reply and "2.16%" in reply
    assert "0.58 percentage points" in reply
    assert "BDT 9,200.00" in reply
    assert "hidden FX margin" in reply
    assert body["mode"] == "template"
    assert body["model_version"] == "template-v1"
    assert body["guard"]["status"] == "passed"
    assert body["facts_used"] and all(f["id"] in body["facts_used"] for f in body["facts"])
    assert set(numbers_in(reply)) <= facts_numbers(body)
    assert body["proposed_actions"] == []
    assert "Indicative" in body["disclaimer"]


def test_the_ranking_answer_flags_the_shortfall_on_provider_c(world: World) -> None:
    quote = world.quote()
    body = ask(world, "Which provider is cheapest?", quote_id=quote["quote_id"]).json()
    assert body["reply"].index("Provider B") < body["reply"].index("Provider C")
    assert "GBP 35.00" in body["reply"]
    assert "OUR avoids that" in body["reply"]


def test_a_question_about_one_provider_gives_its_breakdown(world: World) -> None:
    quote = world.quote()
    body = ask(world, "Explain the shortfall on Provider C", quote_id=quote["quote_id"]).json()
    assert "Provider C (synthetic)" in body["reply"]
    assert "GBP 35.00" in body["reply"]


def test_charge_codes_are_explained_and_our_is_recommended_for_tuition(world: World) -> None:
    body = ask(world, "What do OUR, SHA and BEN mean?").json()
    assert "recommend OUR" in body["reply"]
    assert body["guard"]["status"] == "passed"


def test_deadline_answer_uses_the_planner_dates(world: World) -> None:
    quote = world.quote()
    body = ask(world, "When should I send the payment?", quote_id=quote["quote_id"]).json()
    assert "2026-10-20" in body["reply"] and "2026-10-19" in body["reply"]
    assert "Indicative. Confirm with your AD bank." in body["reply"]
    without = ask(world, "When is the deadline?").json()
    assert "do not have a due date" in without["reply"]


def test_checklist_and_kyc_answers(world: World) -> None:
    docs = ask(world, "What documents do I need for UK tuition?").json()
    assert "Offer or admission letter" in docs["reply"]
    assert "Indicative. Confirm with your AD bank." in docs["reply"]
    kyc = ask(world, "What is my KYC status?").json()
    assert "NEEDS_DOCUMENTS" in kyc["reply"] and "simulated" in kyc["reply"]


def test_limits_answer_says_the_figures_are_not_legal_limits_or_verified(world: World) -> None:
    body = ask(world, "What is the daily limit?").json()
    assert "USD 100,000.00" in body["reply"]
    assert "not legal limits" in body["reply"]
    assert "NOT verified" in body["reply"]
    assert "Indicative. Confirm with your AD bank." in body["reply"]


def test_without_a_quote_the_assistant_says_it_has_no_figures(world: World) -> None:
    body = ask(world, "Why is Provider B cheaper than A?").json()
    assert "do not have a quote" in body["reply"]
    assert not numbers_in(body["reply"])


def test_asking_for_a_draft_returns_a_proposal_and_changes_nothing(world: World) -> None:
    quote = world.quote()
    body = ask(world, "Create a draft with Provider B", quote_id=quote["quote_id"]).json()
    action = body["proposed_actions"][0]
    assert action["tool"] == "create_draft"
    assert action["args"] == {"quote_id": quote["quote_id"], "provider_id": "prov_b"}
    assert action["requires_human"] is True
    assert action["missing"] == ["recipient_id", "reference"]
    assert world.call("GET", "/payments").json()["items"] == []
    proposed = world.audit_rows(action="ai.tool_proposed")
    assert len(proposed) == 1 and proposed[0]["actor_type"] == "ai"
    assert proposed[0]["decision"] == "suggested"


def test_request_approval_is_only_proposed(world: World) -> None:
    world.verify_kyc()
    world.allowlist()
    payment = world.draft()
    body = ask(world, "Please request approval for it", payment_id=payment["payment_id"]).json()
    assert body["proposed_actions"][0]["tool"] == "request_approval"
    assert world.call("GET", f"/payments/{payment['payment_id']}").json()["state"] == "QUOTED"


def test_status_answer_names_what_blocks_approval(world: World) -> None:
    payment = world.draft()
    body = ask(world, "What is the status?", payment_id=payment["payment_id"]).json()
    assert "QUOTED" in body["reply"]
    assert "KYC is not verified" in body["reply"]
