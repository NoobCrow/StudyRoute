import pytest

from app.ai.tools import NOT_AVAILABLE_TO_AI, TOOLS, validate_proposal
from app.domain.constants import ActorKind
from app.domain.rbac import make_actor

AI = make_actor(ActorKind.AI, "usr_ai", owner_id="usr_p", on_behalf_of="usr_p")
PARENT = make_actor(ActorKind.PARENT, "usr_p", owner_id="usr_p")


@pytest.mark.parametrize("name", sorted(NOT_AVAILABLE_TO_AI))
def test_privileged_tools_are_never_available_to_the_ai(name: str) -> None:
    decision = validate_proposal(AI, name, {})
    assert not decision.allowed and decision.reason == "NOT_AVAILABLE_TO_AI"
    assert name not in TOOLS


def test_the_two_proposal_tools_pass_the_ai_permission_check() -> None:
    draft = validate_proposal(AI, "create_draft", {"quote_id": "qte_1", "provider_id": "prov_b"})
    assert draft.allowed and draft.spec is not None
    assert validate_proposal(AI, "request_approval", {"payment_id": "pay_1"}).allowed


def test_unknown_tools_extra_args_and_odd_values_are_rejected() -> None:
    assert validate_proposal(AI, "delete_everything", {}).reason == "UNKNOWN_TOOL"
    assert validate_proposal(AI, "create_draft", {"amount": "1"}).reason == "BAD_ARGS"
    assert validate_proposal(AI, "create_draft", {"quote_id": "x; DROP TABLE"}).reason == "BAD_ARGS"
    assert validate_proposal(AI, "create_draft", {"quote_id": 5}).reason == "BAD_ARGS"  # type: ignore[dict-item]


def test_read_tools_are_executed_by_the_orchestrator_not_proposed() -> None:
    assert validate_proposal(AI, "get_quotes", {}).reason == "NOT_A_PROPOSAL"


def test_a_token_without_the_scope_cannot_propose() -> None:
    narrowed = make_actor(
        ActorKind.AI, "usr_ai", owner_id="usr_p", on_behalf_of="usr_p", scopes=frozenset()
    )
    assert validate_proposal(narrowed, "create_draft", {}).reason == "PERMISSION_DENIED"


def test_human_parent_permissions_are_checked_the_same_way() -> None:
    assert validate_proposal(PARENT, "create_draft", {"quote_id": "qte_1"}).allowed
