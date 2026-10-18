"""Backend for any OpenAI-compatible chat-completions endpoint (a different provider).

Kept separate from the Claude backend so each provider uses its own native client code.
"""

from __future__ import annotations

from typing import Any

import httpx

from app.ai.llm import LLMError, LLMResult

MAX_TOKENS = 1500


class OpenAICompatibleLLM:
    provider = "openai_compatible"

    def __init__(
        self,
        *,
        api_key: str,
        model: str,
        base_url: str,
        timeout: float,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self.model = model
        self._url = base_url.rstrip("/") + "/chat/completions"
        self._headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
        self._http = httpx.Client(timeout=timeout, transport=transport)

    def complete(self, *, system: str, user: str) -> LLMResult:
        body: dict[str, Any] = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "response_format": {"type": "json_object"},
            "max_tokens": MAX_TOKENS,
            "temperature": 0,
        }
        try:
            response = self._http.post(self._url, json=body, headers=self._headers)
        except httpx.HTTPError as exc:
            raise LLMError("The model API could not be reached.") from exc
        if response.status_code != 200:
            raise LLMError(f"The model API returned HTTP {response.status_code}.")
        try:
            payload = response.json()
            choice = payload["choices"][0]
            text = choice["message"]["content"] or ""
        except (ValueError, KeyError, IndexError, TypeError) as exc:
            raise LLMError("The model API returned an unexpected response.") from exc
        usage = payload.get("usage") or {}
        return LLMResult(
            text=text,
            model=str(payload.get("model") or self.model),
            input_tokens=usage.get("prompt_tokens"),
            output_tokens=usage.get("completion_tokens"),
            request_id=response.headers.get("x-request-id"),
            stop_reason=choice.get("finish_reason"),
        )
