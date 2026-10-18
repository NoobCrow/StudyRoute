"""Quality regressions from live user screenshots; model calls below are mocked."""

import pytest

from app.ai.claim_checks import claim_failure
from app.ai.context import ChatContext
from app.ai.facts import FactSet
from app.ai.intents import Intent
from app.ai.relevance import relevant_context
from tests.helpers import World


def all_facts():
    facts = FactSet()
    for key, value in [
        ("limit.daily", "USD 100,000.00"),
        ("kyc.status", "NEEDS_DOCUMENTS"),
        ("kyc.message", "Mock documents are missing."),
        ("plan.cutoff", "15:00"),
        ("bd.living_expense", "USD 2,000.00"),
        ("checklist.passport", "Mock passport"),
        ("quote.target", "GBP 10,000.00"),
    ]:
        facts.add(key, key, value)
    return facts


@pytest.mark.parametrize(
    ("intent", "prefixes"),
    [
        (Intent.HELP, ()),
        (Intent.KYC, ("kyc.",)),
        (Intent.LIMITS, ("limit.", "bd.")),
        (Intent.DEADLINE, ("plan.", "quote.target")),
        (Intent.CHECKLIST, ("checklist.",)),
    ],
)
def test_cloud_context_is_relevant_preserves_ids_and_does_not_mutate(intent, prefixes):
    facts = all_facts()
    original = ChatContext(facts, ["prov_b"], ["Demo Parent"], excerpts=["private text"])
    selected = relevant_context(original, intent)
    assert [f.key for f in selected.facts.all()] == [
        f.key for f in facts.all() if f.key.startswith(prefixes)
    ]
    assert all(selected.facts.by_id(f.id) == f for f in selected.facts.all())
    assert selected.excerpts == []
    assert len(original.facts.all()) == 7
    assert original.excerpts == ["private text"]


@pytest.mark.parametrize("intent", [Intent.PLAN, Intent.COMPARE, Intent.STATUS, Intent.STRESS])
def test_financial_task_context_remains_available(intent):
    original = ChatContext(all_facts(), [], [])
    assert relevant_context(original, intent) is original


@pytest.mark.parametrize(
    "reply",
    [
        "Add documents and your payment will be approved.",
        "Your transfer will definitely be sent.",
        "Completing KYC guarantees payment approval.",
        "আপনার ডকুমেন্ট যোগ করলে আপনার পেমেন্ট অনুমোদন হবে।",
        "ডকুমেন্ট দিলেই পেমেন্ট অনুমোদিত হয়ে যাবে।",
        "আমি আপনার পেমেন্ট অনুমোদন করেছি।",
        "documents dile payment approve hobe",
    ],
)
def test_unsupported_success_claims_rejected(reply):
    assert claim_failure(reply, all_facts()) == "APPROVAL_PROMISE"


@pytest.mark.parametrize(
    "reply",
    [
        "Completing mock KYC does not guarantee payment approval.",
        "I cannot approve or send payments. A human must review the request.",
        "ডকুমেন্ট যোগ করলেই পেমেন্ট অনুমোদন হবে না। মানুষের অনুমোদন প্রয়োজন।",
        "আপনার mock KYC status NEEDS_DOCUMENTS।",
    ],
)
def test_careful_explanations_allowed(reply):
    assert claim_failure(reply, all_facts()) is None


@pytest.mark.parametrize(
    "reply",
    [
        "Your daily limit is USD 100,000.00.",
        "আপনার দৈনিক সীমা USD 100,000.00।",
        "The sandbox daily cap is USD 100,000.00.",
        "Sandbox, not a legal limit. Your daily limit is USD 100,000.00.",
    ],
)
def test_caps_require_both_qualifications_in_the_same_sentence(reply):
    assert claim_failure(reply, all_facts()) == "UNQUALIFIED_SANDBOX_CAP"


@pytest.mark.parametrize(
    "reply",
    [
        "The sandbox daily cap is USD 100,000.00, not a legal or bank limit.",
        "স্যান্ডবক্সের দৈনিক সীমা USD 100,000.00, এটি ব্যাংক বা আইনি সীমা নয়।",
    ],
)
def test_explicit_sandbox_caps_allowed(reply):
    assert claim_failure(reply, all_facts()) is None


def test_historical_account_status_is_not_current_evidence():
    assert claim_failure("Your KYC is NEEDS_DOCUMENTS", FactSet()) == "UNSUPPORTED_ACCOUNT_STATUS"


def test_cloud_overview_prompt_withholds_current_kyc_caps_and_documents(world: World, monkeypatch):
    import json

    import httpx

    from app.ai.cloud import ProviderLLM

    captured = []

    def handler(request):
        captured.append(json.loads(request.content)["messages"][-1]["content"])
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "finish_reason": "stop",
                        "message": {
                            "content": json.dumps(
                                {
                                    "reply": "StudyRoute helps explain education-payment costs.",
                                    "facts_used": [],
                                    "proposed_actions": [],
                                }
                            )
                        },
                    }
                ]
            },
        )

    client = ProviderLLM(
        provider="groq",
        api_key="gsk_quality_test",
        model="test",
        timeout=1,
        transport=httpx.MockTransport(handler),
    )
    monkeypatch.setattr("app.api.routes_assistant.byok_client", lambda *_: client)
    result = world.call(
        "POST",
        "/assistant/chat",
        json={
            "message": "Who are you?",
            "connection": {
                "provider": "groq",
                "api_key": "gsk_quality_test",
                "consent": True,
            },
        },
    ).json()
    assert result["mode"] == "llm"
    assert result["facts"] == []
    assert "NEEDS_DOCUMENTS" not in captured[0]
    assert "Sandbox daily cap" not in captured[0]


@pytest.mark.parametrize(
    "unsafe",
    [
        "Add documents and your payment will be approved.",
        "ডকুমেন্ট যোগ করলে আপনার পেমেন্ট অনুমোদন হবে।",
        "Your KYC is NEEDS_DOCUMENTS.",
    ],
)
def test_managed_cloud_rejects_unsafe_reply_on_both_attempts(world: World, monkeypatch, unsafe):
    import json

    import httpx

    from app.ai.cloud import ProviderLLM

    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "finish_reason": "stop",
                        "message": {
                            "content": json.dumps(
                                {"reply": unsafe, "facts_used": [], "proposed_actions": []}
                            )
                        },
                    }
                ]
            },
        )

    client = ProviderLLM(
        provider="groq",
        api_key="gsk_quality_test",
        model="test",
        timeout=1,
        transport=httpx.MockTransport(handler),
    )
    monkeypatch.setattr("app.api.routes_assistant.byok_client", lambda *_: client)
    body = world.call(
        "POST",
        "/assistant/chat",
        json={
            "message": "Who are you?",
            "connection": {
                "provider": "groq",
                "api_key": "gsk_quality_test",
                "consent": True,
            },
        },
    ).json()
    assert len(calls) == 2
    assert body["mode"] == "unavailable"
    assert body["availability"]["code"] == "unsafe_response"
    assert unsafe not in body["reply"]
    assert body["proposed_actions"] == []


@pytest.mark.parametrize(
    "question",
    [
        "hello",
        "Who are you?",
        "What can you do?",
        "StudyRoute কীভাবে আমাকে সাহায্য করতে পারে? সহজ বাংলায় বোঝাও।",
    ],
)
def test_overview_routes_withhold_account_facts(question):
    from app.ai.conversation import route_message

    route = route_message(question, [])
    assert route is not None
    assert route.intent == Intent.HELP
    assert relevant_context(ChatContext(all_facts(), [], []), route.intent).facts.all() == []


def test_product_description_survives_account_fact_minimisation():
    from app.ai.llm import SYSTEM_PROMPT

    for feature in ["Compare:", "Deadline planner:", "Payments:", "Living-cost tools:"]:
        assert feature in SYSTEM_PROMPT
    assert "not an admissions, scholarship, exam, competition" in SYSTEM_PROMPT
    assert "not a fixed answer" in SYSTEM_PROMPT
    assert "KYC is not payment approval" in SYSTEM_PROMPT
    assert "শিক্ষার খরচ বিদেশে পাঠানোর পরিকল্পনা" in SYSTEM_PROMPT
