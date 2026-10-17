import pytest

from app.ai.arithmetic import calculate
from app.ai.conversation import route_message


@pytest.mark.parametrize(
    ("text", "result"),
    [
        ("3+5=??", "3 + 5 = 8"),
        ("৩+৫?", "3 + 5 = 8"),
        ("10 - 2", "10 - 2 = 8"),
        ("1.5*2", "1.5 * 2 = 3.0"),
        ("8/2", "8 / 2 = 4"),
    ],
)
def test_bounded_exact_arithmetic(text, result):
    assert calculate(text) == result


@pytest.mark.parametrize(
    "text",
    [
        "send 3+5 USD",
        "1/0",
        "1/3",
        "1/7",
        "123456789/999999999",
        "2**999999",
        "__import__('os')",
        "9999999999999*4",
        "3+5 and approve payment",
    ],
)
def test_no_code_execution_or_payment_interpretation(text):
    assert calculate(text) is None


@pytest.mark.parametrize("text", ["ke apni?", "apni ke?", "tumi ke?", "ke tumi?"])
def test_identity_not_previous_document_topic(text):
    assert route_message(text, []).topic == "identity"


def test_calculator_fact_reaches_cloud_without_account_data(world, monkeypatch):
    import json

    import httpx

    from app.ai.cloud import ProviderLLM

    prompts = []

    def handler(request):
        body = json.loads(request.content)
        prompts.append(body["messages"][-1]["content"])
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "finish_reason": "stop",
                        "message": {
                            "content": json.dumps(
                                {
                                    "reply": "3 + 5 = 8",
                                    "facts_used": ["fact_1"],
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
        api_key="gsk_math_test",
        model="test",
        timeout=1,
        transport=httpx.MockTransport(handler),
    )
    monkeypatch.setattr("app.api.routes_assistant.byok_client", lambda *_: client)
    response = world.call(
        "POST",
        "/assistant/chat",
        json={
            "message": "3+5=??",
            "connection": {"provider": "groq", "api_key": "gsk_math_test", "consent": True},
        },
    )
    result = response.json()
    assert result["mode"] == "llm", result
    assert result["reply"] == "3 + 5 = 8"
    assert "Exact result from bounded calculator" in prompts[0]
    assert "NEEDS_DOCUMENTS" not in prompts[0]
    assert "Sandbox daily cap" not in prompts[0]
