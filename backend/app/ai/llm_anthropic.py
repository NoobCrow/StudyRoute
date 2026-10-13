"""Claude backend, built on the official Anthropic SDK (Messages API).

JSON-only replies use structured outputs (output_config.format with a JSON schema). The model
id is pinned by the operator and the id the API reports is returned for the audit log.
Sampling parameters are not sent: current Claude models reject them.
"""

from __future__ import annotations

from typing import Any

from app.ai.llm import RESPONSE_SCHEMA, LLMError, LLMRefused, LLMResult

# Models on which output_config.effort is accepted. Older models would return a 400.
_EFFORT_PREFIXES = (
    "claude-fable-5", "claude-mythos-5", "claude-opus-5", "claude-sonnet-5",
    "claude-haiku-5", "claude-opus-4-8", "claude-opus-4-7", "claude-opus-4-6", "claude-sonnet-4-6",
)  # fmt: skip
MAX_TOKENS = 4096


def supports_effort(model: str) -> bool:
    return model.startswith(_EFFORT_PREFIXES)


class AnthropicLLM:
    provider = "anthropic"

    def __init__(
        self, *, api_key: str, model: str, timeout: float, client: Any | None = None
    ) -> None:
        self.model = model
        if client is not None:
            self._client = client
        else:
            import anthropic

            self._client = anthropic.Anthropic(api_key=api_key, timeout=timeout, max_retries=1)

    def _output_config(self) -> dict[str, Any]:
        config: dict[str, Any] = {"format": {"type": "json_schema", "schema": RESPONSE_SCHEMA}}
        if supports_effort(self.model):
            config["effort"] = "low"  # a short explanation does not need deep reasoning
        return config

    def complete(self, *, system: str, user: str) -> LLMResult:
        import anthropic

        try:
            response = self._client.messages.create(
                model=self.model,
                max_tokens=MAX_TOKENS,
                system=system,
                messages=[{"role": "user", "content": user}],
                output_config=self._output_config(),
            )
        except anthropic.RateLimitError as exc:
            raise LLMError("The model is rate limited.") from exc
        except anthropic.APIStatusError as exc:
            raise LLMError(f"The model API returned HTTP {exc.status_code}.") from exc
        except anthropic.APIConnectionError as exc:
            raise LLMError("The model API could not be reached.") from exc
        if response.stop_reason == "refusal":
            raise LLMRefused("The model declined to answer.")
        if response.stop_reason == "max_tokens":
            raise LLMError("The model reply was cut off.")
        text = next((block.text for block in response.content if block.type == "text"), "")
        usage = getattr(response, "usage", None)
        return LLMResult(
            text=text,
            model=str(response.model),
            input_tokens=getattr(usage, "input_tokens", None),
            output_tokens=getattr(usage, "output_tokens", None),
            request_id=getattr(response, "_request_id", None),
            stop_reason=response.stop_reason,
        )
