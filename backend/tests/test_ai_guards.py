import json

import pytest

from app.ai.facts import FactSet
from app.ai.guards import GuardFailure, parse_llm_json, validate_llm_output
from app.domain.constants import ActorKind
from app.domain.rbac import make_actor

AI = make_actor(ActorKind.AI, "usr_ai", owner_id="usr_p", on_behalf_of="usr_p")


def facts() -> FactSet:
    f = FactSet()
    f.add("b.cost", "Provider B cost", "1.58%")
    f.add("b.total", "Provider B total", "BDT 25,300.00")
    return f


def validate(reply: str, **extra):
    parsed = {"reply": reply, "facts_used": ["fact_1", "fact_999"], "proposed_actions": []}
    parsed.update(extra)
    return validate_llm_output(parsed, facts=facts(), actor=AI, legal_question=False)


def test_a_clean_reply_passes_and_unknown_fact_ids_are_dropped() -> None:
    result = validate("Provider B costs 1.58%, which is BDT 25,300 in total.")
    assert result.facts_used == ["fact_1"]


def test_an_invented_number_fails_the_guard() -> None:
    with pytest.raises(GuardFailure) as caught:
        validate("Provider B costs 3.99% in total.")
    assert caught.value.code == "NUMBER_GUARD"
    assert "3.99" in caught.value.detail


@pytest.mark.parametrize(
    "reply",
    ["I have approved the payment.", "I approved it for you", "The payment has been submitted."],
)
def test_claiming_an_action_fails(reply: str) -> None:
    with pytest.raises(GuardFailure) as caught:
        validate(reply)
    assert caught.value.code == "ACTION_CLAIM"


@pytest.mark.parametrize(
    "reply", ["That is legal.", "This is within the limit.", "It is perfectly legal to send."]
)
def test_calling_something_legal_or_within_the_limit_fails(reply: str) -> None:
    with pytest.raises(GuardFailure) as caught:
        validate(reply)
    assert caught.value.code == "LEGAL_CLAIM"


def test_refusal_wording_is_not_mistaken_for_a_claim() -> None:
    validate("I cannot approve payments. I cannot say whether it is legal or within a limit.")


def test_forbidden_tool_proposals_fail_and_good_ones_are_kept_as_human_only() -> None:
    bad = {"proposed_actions": [{"tool": "approve", "args_json": "{}"}]}
    with pytest.raises(GuardFailure) as caught:
        validate("Done.", **bad)
    assert caught.value.code == "TOOL_NOT_ALLOWED"
    good = {
        "proposed_actions": [
            {"tool": "create_draft", "args_json": json.dumps({"provider_id": "prov_b"})}
        ]
    }
    proposals = validate("Here is a draft.", **good).proposals
    assert proposals == [
        {
            "tool": "create_draft",
            "args": {"provider_id": "prov_b"},
            "requires_human": True,
            "missing": [],
        }
    ]


def test_malformed_arguments_are_dropped_not_executed() -> None:
    odd = {"proposed_actions": [{"tool": "create_draft", "args_json": "not json"}]}
    assert validate("ok", **odd).proposals == []


def test_bad_shapes_are_rejected() -> None:
    for parsed in ({}, {"reply": ""}, {"reply": 5}, {"reply": "x" * 2001}):
        with pytest.raises(GuardFailure):
            validate_llm_output(parsed, facts=facts(), actor=AI, legal_question=False)


def test_a_legal_question_always_gets_the_indicative_sentence() -> None:
    parsed = {"reply": "I cannot confirm that.", "facts_used": [], "proposed_actions": []}
    result = validate_llm_output(parsed, facts=facts(), actor=AI, legal_question=True)
    assert result.reply.endswith("Indicative. Confirm with your AD bank.")


def test_json_is_extracted_from_surrounding_text() -> None:
    assert parse_llm_json('Sure! {"reply": "hi"} Bye')["reply"] == "hi"
    with pytest.raises(GuardFailure):
        parse_llm_json("no json at all")
