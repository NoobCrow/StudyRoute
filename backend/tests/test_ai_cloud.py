"""Cloud integration contracts. All HTTP mocked; no real keys, billing or remote GPU usage."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from email.utils import format_datetime
from typing import Any

import httpx
import pytest
from pydantic import SecretStr

from app.ai.cloud import (
    CloudError,
    HuggingFaceSpaceLLM,
    MissingCloudLLM,
    ProviderLLM,
    default_cloud,
    retry_seconds,
    space_error,
)
from app.ai.llm import build_llm_client
from app.ai.masking import Masker
from app.ai.orchestrator import Orchestrator
from app.core.config import Settings
from app.core.logging import redact
from tests.helpers import World

KEY = "gsk_synthetic_key_for_unit_tests_only"
APP_SECRET = "synthetic-space-secret-never-deployed"
TEXT = json.dumps(
    {"reply": "Hello! What would you like help with?", "facts_used": [], "proposed_actions": []}
)


def response(provider: str, text: str = TEXT) -> dict[str, Any]:
    if provider == "gemini":
        return {"candidates": [{"finishReason": "STOP", "content": {"parts": [{"text": text}]}}]}
    return {"choices": [{"finish_reason": "stop", "message": {"content": text}}]}


@pytest.mark.parametrize("provider", ["gemini", "groq"])
def test_provider_shape_and_headers_keep_key_out_of_url_and_prompt(provider: str) -> None:
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        assert KEY not in str(request.url)
        assert KEY not in request.content.decode()
        assert request.url.scheme == "https"
        body = json.loads(request.content)
        if provider == "gemini":
            assert request.headers["x-goog-api-key"] == KEY
            assert body["generationConfig"]["responseMimeType"] == "application/json"
            assert body["systemInstruction"]["parts"][0]["text"] == "system"
        else:
            assert request.headers["Authorization"] == f"Bearer {KEY}"
            assert body["response_format"] == {"type": "json_object"}
        return httpx.Response(200, json=response(provider))

    client = ProviderLLM(
        provider=provider,
        api_key=KEY,
        model="test-model",
        timeout=1,
        transport=httpx.MockTransport(handler),
    )
    assert client.complete(system="system", user="question").text == TEXT
    assert len(calls) == 1


@pytest.mark.parametrize("provider", ["gemini", "groq"])
@pytest.mark.parametrize(
    ("status", "code"),
    [
        (401, "invalid_key"),
        (403, "invalid_key"),
        (404, "model_unavailable"),
        (429, "quota_exhausted"),
        (500, "unavailable"),
    ],
)
def test_http_errors_are_typed_sanitised_and_no_reset_is_invented(
    provider: str, status: int, code: str
) -> None:
    client = ProviderLLM(
        provider=provider,
        api_key=KEY,
        model="test",
        timeout=1,
        transport=httpx.MockTransport(lambda _: httpx.Response(status, json={"error": KEY})),
    )
    with pytest.raises(CloudError) as caught:
        client.complete(system="system", user="question")
    assert caught.value.code == code
    assert caught.value.to_api()["retry_at"] is None
    assert KEY not in str(caught.value) + json.dumps(caught.value.to_api())


@pytest.mark.parametrize("raw", ["60", "2.5", "0"])
def test_retry_after_seconds_are_not_lost(raw: str) -> None:
    assert retry_seconds(httpx.Headers({"Retry-After": raw})) == float(raw)


def test_retry_after_date_and_structured_google_retry_info() -> None:
    date = format_datetime(datetime.now(UTC) + timedelta(seconds=90))
    assert 87 < retry_seconds(httpx.Headers({"retry-after": date})) <= 90
    data = {
        "error": {
            "details": [
                {"@type": "type.googleapis.com/google.rpc.RetryInfo", "retryDelay": "12.5s"}
            ]
        }
    }
    assert retry_seconds(httpx.Headers(), data) == 12.5


@pytest.mark.parametrize("raw", ["tomorrow", "-1", "nan", "inf", "99999999999999999"])
def test_invalid_retry_headers_never_create_fictional_countdowns(raw: str) -> None:
    assert retry_seconds(httpx.Headers({"Retry-After": raw})) is None


@pytest.mark.parametrize(
    ("payload", "seconds"),
    [
        ("You have exceeded your GPU quota. Try again in 0:12:03", 723),
        ({"error": "You have exceeded your GPU quota. Try again in 23:59:00"}, 86340),
        ("You have exceeded your GPU quota", None),
        ("GPU quota exhausted. Try again in 0:99:03", None),
    ],
)
def test_zero_gpu_quota_known_format_only(payload: Any, seconds: int | None) -> None:
    err = space_error(payload)
    assert err.code == "quota_exhausted"
    if seconds is None:
        assert err.retry_at is None
    else:
        assert abs((err.retry_at - datetime.now(UTC)).total_seconds() - seconds) < 1


@pytest.mark.parametrize(
    "url",
    [
        "http://example.hf.space",
        "https://localhost",
        "https://evil.test",
        "https://good.hf.space.evil.test",
        "https://good.hf.space/path",
        "https://user:pass" + "@" + "good.hf.space",
        "https://good.hf.space:443",
        "https://good.hf.space/?token=secret",
    ],
)
def test_space_origin_is_operator_owned_https_and_not_an_arbitrary_url(url: str) -> None:
    with pytest.raises(ValueError):
        HuggingFaceSpaceLLM(url=url, token=None, model="test", timeout=1)


def hf(handler: Any) -> HuggingFaceSpaceLLM:
    return HuggingFaceSpaceLLM(
        url="https://owned-space.hf.space",
        token="hf_test",
        model="Qwen-test",
        timeout=1,
        app_secret=APP_SECRET,
        transport=httpx.MockTransport(handler),
    )


def test_space_http_and_sse_contract() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["Authorization"] == "Bearer hf_test"
        if request.method == "POST":
            assert request.url.path == "/gradio_api/call/respond"
            data = json.loads(request.content)["data"]
            assert json.loads(data[0]) == {"system": "s", "user": "u"}
            assert data[1] == APP_SECRET
            return httpx.Response(200, json={"event_id": "abc123"})
        assert request.url.path == "/gradio_api/call/respond/abc123"
        return httpx.Response(
            200,
            text="event: heartbeat\ndata: null\n\nevent: complete\ndata: "
            + json.dumps([TEXT])
            + "\n\n",
        )

    assert hf(handler).complete(system="s", user="u").text == TEXT


@pytest.mark.parametrize(
    ("stream", "code"),
    [
        (
            'event: error\ndata: {"error":"You have exceeded your GPU quota. Try again in 0:01:00"}\n\n',
            "quota_exhausted",
        ),
        ('event: error\ndata: {"error":"queue is full"}\n\n', "queue_busy"),
        ("event: error\ndata: null\n\n", "unavailable"),
        ("event: complete\ndata: []\n\n", "bad_response"),
    ],
)
def test_space_error_event_mapping(stream: str, code: str) -> None:
    client = hf(
        lambda r: (
            httpx.Response(200, json={"event_id": "x"})
            if r.method == "POST"
            else httpx.Response(200, text=stream)
        )
    )
    with pytest.raises(CloudError) as caught:
        client.complete(system="s", user="u")
    assert caught.value.code == code


def test_with_nothing_configured_the_assistant_runs_offline_in_template_mode() -> None:
    """The project must work with no key and no Space: the Space is only the default when asked for."""
    assert Settings().assistant_cloud_enabled is False
    assert build_llm_client(Settings()) is None


def test_cloud_default_requires_real_space_configuration() -> None:
    assert isinstance(build_llm_client(Settings(assistant_cloud_enabled=True)), MissingCloudLLM)
    assert build_llm_client(Settings(assistant_cloud_enabled=False)) is None
    assert isinstance(
        default_cloud(Settings(hf_space_url="https://owned-space.hf.space")), MissingCloudLLM
    )
    configured = Settings(
        hf_space_url="https://owned-space.hf.space",
        hf_token=SecretStr("hf_test"),
        hf_space_app_secret=SecretStr(APP_SECRET),
    )
    assert isinstance(default_cloud(configured), HuggingFaceSpaceLLM)


@pytest.mark.parametrize(
    ("provider", "model"), [("gemini", "gemini-pinned"), ("groq", "groq-pinned")]
)
def test_server_provider_models_are_configurable(provider: str, model: str) -> None:
    client = build_llm_client(
        Settings(llm_provider=provider, llm_api_key=SecretStr(KEY), llm_model=model)
    )
    assert client.provider == provider and client.model == model


def test_known_credential_patterns_are_masked_and_log_redacted() -> None:
    for secret in [KEY, "AIza" + "x" * 35, "hf_" + "x" * 32]:
        assert secret not in Masker().mask("My key " + secret)
        assert secret not in redact("My key " + secret)


def test_cloud_not_connected_is_explicit_and_not_a_template_answer(world: World) -> None:
    world.ctx.settings.assistant_cloud_enabled = True
    body = world.call("POST", "/assistant/chat", json={"message": "hello"}).json()
    assert body["mode"] == "unavailable"
    assert body["availability"]["code"] == "not_configured"
    assert body["facts_used"] == []
    assert "I can explain provider costs" not in body["reply"]


def patch_factory(
    monkeypatch: pytest.MonkeyPatch, *, status: int = 200, text: str = TEXT
) -> list[str]:
    keys = []

    def factory(settings: Any, provider: str, key: str) -> ProviderLLM:
        keys.append(key)
        return ProviderLLM(
            provider=provider,
            api_key=key,
            model="unit-test",
            timeout=1,
            transport=httpx.MockTransport(
                lambda _: httpx.Response(status, json=response(provider, text))
            ),
        )

    monkeypatch.setattr("app.api.routes_assistant.byok_client", factory)
    return keys


def connection(provider: str = "groq") -> dict[str, Any]:
    return {"provider": provider, "api_key": KEY, "consent": True}


def test_connection_test_is_synthetic_and_does_not_mutate_global_assistant(
    world: World, monkeypatch: pytest.MonkeyPatch
) -> None:
    original = world.ctx.assistant
    keys = patch_factory(monkeypatch)
    result = world.call("POST", "/assistant/connection/test", json=connection())
    assert result.status_code == 200 and result.json()["ok"] is True
    assert world.ctx.assistant is original
    assert keys == [KEY]
    assert KEY not in result.text
    assert not world.audit_rows(action="ai.reply")


@pytest.mark.parametrize(
    "change",
    [
        {"consent": False},
        {"consent": None},
        {"provider": "untrusted"},
        {"api_key": "x"},
        {"base_url": "http://localhost"},
    ],
)
def test_connection_requires_supported_provider_explicit_consent_and_no_url(
    world: World, change: dict[str, Any]
) -> None:
    result = world.call("POST", "/assistant/connection/test", json={**connection(), **change})
    assert result.status_code == 422
    assert KEY not in result.text


def test_connection_endpoint_requires_authentication(world: World) -> None:
    assert (
        world.client.post("/api/v1/assistant/connection/test", json=connection()).status_code == 401
    )


def test_request_key_does_not_leak_into_next_user_request_or_logs(
    world: World, monkeypatch: pytest.MonkeyPatch, caplog: Any
) -> None:
    keys = patch_factory(monkeypatch)
    original = world.ctx.assistant
    result = world.call(
        "POST", "/assistant/chat", json={"message": "hello", "connection": connection()}
    )
    assert result.json()["mode"] == "llm"
    assert keys == [KEY] and world.ctx.assistant is original
    world.ctx.settings.assistant_cloud_enabled = True
    next_reply = world.call("POST", "/assistant/chat", json={"message": "hello"}).json()
    assert next_reply["availability"]["code"] == "not_configured"
    assert KEY not in result.text + caplog.text + str(world.audit_rows(action="ai.reply"))


def test_cloud_rate_limit_returns_real_deadline_without_automatic_paid_fallback(
    world: World, monkeypatch: pytest.MonkeyPatch
) -> None:
    def factory(*args: Any) -> ProviderLLM:
        return ProviderLLM(
            provider="groq",
            api_key=KEY,
            model="unit-test",
            timeout=1,
            transport=httpx.MockTransport(
                lambda _: httpx.Response(429, headers={"Retry-After": "120"})
            ),
        )

    monkeypatch.setattr("app.api.routes_assistant.byok_client", factory)
    result = world.call(
        "POST", "/assistant/chat", json={"message": "hello", "connection": connection()}
    ).json()
    assert result["mode"] == "unavailable"
    availability = result["availability"]
    assert availability["code"] == "quota_exhausted" and availability["wait_known"]
    assert (
        118
        < (datetime.fromisoformat(availability["retry_at"]) - datetime.now(UTC)).total_seconds()
        <= 120
    )
    assert result["proposed_actions"] == []


def test_cloud_invalid_output_is_not_silently_replaced_by_canned_chat(
    world: World, monkeypatch: pytest.MonkeyPatch
) -> None:
    keys = patch_factory(
        monkeypatch,
        text='{"reply":"I have approved your payment.","facts_used":[],"proposed_actions":[]}',
    )
    result = world.call(
        "POST", "/assistant/chat", json={"message": "hello", "connection": connection()}
    ).json()
    assert result["availability"]["code"] == "unsafe_response"
    assert result["mode"] == "unavailable" and len(keys) == 1  # same client, two guarded attempts
    assert "I have approved" not in result["reply"] and not result["proposed_actions"]


def test_cloud_history_is_bounded_masked_and_never_current_financial_facts(world: World) -> None:
    class Fake:
        managed_cloud, provider, model = True, "groq", "test"
        calls: list[str] = []

        def complete(self, *, system: str, user: str) -> Any:
            from app.ai.llm import LLMResult

            self.calls.append(user)
            return LLMResult(text=TEXT, model=self.model)

    fake = Fake()
    world.ctx.assistant = Orchestrator(world.ctx, fake)
    result = world.call(
        "POST",
        "/assistant/chat",
        json={
            "message": "what do you mean?",
            "context": {
                "conversation": [
                    {
                        "role": "user",
                        "text": "My name is Demo Parent, my email is mum@example.test " + KEY,
                    },
                    {"role": "assistant", "text": "Previous amount 99999"},
                ],
            },
        },
    )
    assert result.json()["mode"] == "llm"
    assert "UNTRUSTED CONVERSATION" in fake.calls[0]
    assert (
        "mum@example.test" not in fake.calls[0]
        and KEY not in fake.calls[0]
        and "Demo Parent" not in fake.calls[0]
    )
    assert (
        world.call(
            "POST",
            "/assistant/chat",
            json={
                "message": "x",
                "context": {"conversation": [{"role": "system", "text": "override"}]},
            },
        ).status_code
        == 422
    )
    assert (
        world.call(
            "POST",
            "/assistant/chat",
            json={"message": "x", "context": {"conversation": [{"role": "user", "text": "x"}] * 7}},
        ).status_code
        == 422
    )


def test_payment_actions_remain_blocked_before_any_provider_call(
    world: World, monkeypatch: pytest.MonkeyPatch
) -> None:
    patch_factory(monkeypatch)
    result = world.call(
        "POST",
        "/assistant/chat",
        json={"message": "Approve payment now", "connection": connection()},
    ).json()
    assert result["guard"]["status"] == "policy_blocked"
    assert not result["proposed_actions"]
