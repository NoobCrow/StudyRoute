"""LLM backends: request shape, pinned model, error mapping and template mode."""

from __future__ import annotations

import json
from types import SimpleNamespace
from typing import Any

import httpx
import pytest
from pydantic import SecretStr

from app.ai.llm import (
    DEFAULT_ANTHROPIC_MODEL,
    RESPONSE_SCHEMA,
    SYSTEM_PROMPT,
    LLMError,
    LLMRefused,
    build_llm_client,
)
from app.ai.llm_anthropic import AnthropicLLM, supports_effort
from app.core.config import Settings

REPLY = '{"reply":"ok","facts_used":[],"proposed_actions":[]}'


class FakeMessages:
    def __init__(self, response: Any = None, error: Exception | None = None) -> None:
        self.calls: list[dict[str, Any]] = []
        self._response = response
        self._error = error

    def create(self, **kwargs: Any) -> Any:
        self.calls.append(kwargs)
        if self._error:
            raise self._error
        return self._response


def fake_response(**overrides: Any) -> Any:
    base = {
        "content": [SimpleNamespace(type="text", text=REPLY)],
        "model": "claude-opus-5-5",
        "stop_reason": "end_turn",
        "usage": SimpleNamespace(input_tokens=120, output_tokens=40),
        "_request_id": "req_abc",
    }
    base.update(overrides)
    return SimpleNamespace(**base)


def anthropic_with(messages: FakeMessages, model: str = "claude-opus-5-5") -> AnthropicLLM:
    client = SimpleNamespace(messages=messages)
    return AnthropicLLM(api_key="sk-test", model=model, timeout=5, client=client)


def settings_for(**kwargs: Any) -> Settings:
    return Settings(**kwargs)


def test_template_mode_is_the_default_without_a_key() -> None:
    assert build_llm_client(settings_for()) is None
    assert build_llm_client(settings_for(llm_provider="anthropic")) is None
    empty = settings_for(llm_provider="anthropic", llm_api_key=SecretStr(""))
    assert build_llm_client(empty) is None


def test_an_anthropic_key_builds_a_client_with_the_pinned_or_default_model() -> None:
    key = SecretStr("sk-test")
    pinned = build_llm_client(
        settings_for(llm_provider="anthropic", llm_api_key=key, llm_model="claude-sonnet-5-5")
    )
    assert pinned is not None
    assert pinned.model == "claude-sonnet-5-5"
    default = build_llm_client(settings_for(llm_provider="anthropic", llm_api_key=key))
    assert default is not None
    assert default.model == DEFAULT_ANTHROPIC_MODEL


def test_openai_compatible_needs_a_model_and_a_base_url() -> None:
    incomplete = settings_for(llm_provider="openai_compatible", llm_api_key=SecretStr("k"))
    assert build_llm_client(incomplete) is None


def test_the_anthropic_request_uses_structured_json_and_no_sampling_parameters() -> None:
    messages = FakeMessages(fake_response())
    result = anthropic_with(messages).complete(system=SYSTEM_PROMPT, user="FACTS ...")
    call = messages.calls[0]
    assert call["model"] == "claude-opus-5-5"
    assert call["system"] == SYSTEM_PROMPT
    assert call["messages"] == [{"role": "user", "content": "FACTS ..."}]
    assert call["output_config"]["format"] == {"type": "json_schema", "schema": RESPONSE_SCHEMA}
    assert call["output_config"]["effort"] == "low"
    assert call["max_tokens"] >= 1024
    for forbidden in ("temperature", "top_p", "top_k", "thinking", "tools"):
        assert forbidden not in call
    assert result.model == "claude-opus-5-5"
    assert (result.input_tokens, result.output_tokens) == (120, 40)
    assert result.request_id == "req_abc"
    assert json.loads(result.text)["reply"] == "ok"


def test_effort_is_only_sent_to_models_that_accept_it() -> None:
    assert supports_effort("claude-opus-5-5")
    assert supports_effort("claude-haiku-5-5")
    assert not supports_effort("claude-haiku-4-5")
    assert not supports_effort("claude-sonnet-4-5")
    messages = FakeMessages(fake_response())
    anthropic_with(messages, "claude-haiku-4-5").complete(system="s", user="u")
    assert "effort" not in messages.calls[0]["output_config"]


def test_refusals_and_truncation_are_errors_not_replies() -> None:
    refused = anthropic_with(FakeMessages(fake_response(stop_reason="refusal")))
    with pytest.raises(LLMRefused):
        refused.complete(system="s", user="u")
    cut = anthropic_with(FakeMessages(fake_response(stop_reason="max_tokens")))
    with pytest.raises(LLMError):
        cut.complete(system="s", user="u")


def test_api_failures_are_mapped_without_leaking_the_prompt() -> None:
    import anthropic

    request = httpx.Request("POST", "https://api.example.test/v1/messages")
    client = anthropic_with(FakeMessages(error=anthropic.APIConnectionError(request=request)))
    with pytest.raises(LLMError) as caught:
        client.complete(system="s", user="secret prompt text")
    assert "secret prompt text" not in str(caught.value)
