import json
from typing import Any

import httpx
import pytest

from app.ai.llm import LLMError
from app.ai.llm_openai import OpenAICompatibleLLM


def test_openai_compatible_request_and_response_mapping() -> None:
    seen: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        seen["auth"] = request.headers["authorization"]
        seen["body"] = json.loads(request.content)
        return httpx.Response(
            200,
            json={
                "model": "gpt-test-1",
                "choices": [{"message": {"content": '{"reply":"hi"}'}, "finish_reason": "stop"}],
                "usage": {"prompt_tokens": 9, "completion_tokens": 3},
            },
        )

    llm = OpenAICompatibleLLM(
        api_key="k",
        model="gpt-test",
        base_url="https://llm.example.test/v1/",
        timeout=5,
        transport=httpx.MockTransport(handler),
    )
    result = llm.complete(system="sys", user="usr")
    assert seen["url"] == "https://llm.example.test/v1/chat/completions"
    assert seen["auth"] == "Bearer k"
    assert seen["body"]["response_format"] == {"type": "json_object"}
    assert seen["body"]["messages"][0] == {"role": "system", "content": "sys"}
    assert result.model == "gpt-test-1"
    assert result.input_tokens == 9


def test_openai_compatible_errors_are_mapped() -> None:
    llm = OpenAICompatibleLLM(
        api_key="k",
        model="m",
        base_url="https://x.test",
        timeout=5,
        transport=httpx.MockTransport(lambda request: httpx.Response(500)),
    )
    with pytest.raises(LLMError):
        llm.complete(system="s", user="u")
