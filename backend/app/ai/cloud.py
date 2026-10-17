"""Remote-only inference, typed availability, and request-scoped BYOK clients.

No model weights, credentials cache, arbitrary user-supplied URLs or response-body logs.
Only authenticated callers can select a provider; hosts are fixed/operator-configured.
"""

from __future__ import annotations

import json
import math
import re
import time
from datetime import UTC, datetime, timedelta
from email.utils import parsedate_to_datetime
from typing import Any
from urllib.parse import urlsplit

import httpx

from app.ai.llm import LLMError, LLMResult
from app.core.config import Settings

MESSAGES = {
    "not_configured": (
        "The Hugging Face model is not connected yet. Configure your own Space, or add "
        "a Gemini or Groq API key to continue."
    ),
    "quota_exhausted": (
        "This provider's usage limit has been reached. Use the reported retry time "
        "below, or connect a different provider to continue."
    ),
    "queue_busy": (
        "The Hugging Face queue is busy. An exact waiting time was not supplied. Please "
        "try again later or connect Gemini or Groq."
    ),
    "invalid_key": (
        "The provider rejected the API key or access permissions. Check the key and "
        "model access, then test the connection again."
    ),
    "model_unavailable": (
        "The configured model was not found or is not available to this account. Check "
        "the model setting and provider access."
    ),
    "unavailable": (
        "The cloud model could not be reached or did not finish in time. Please try "
        "again later or connect another provider."
    ),
    "unsafe_response": (
        "The model's answer did not pass StudyRoute's safety checks. No action was "
        "taken. Rephrase your question or try another model."
    ),
    "bad_response": (
        "The provider returned an incomplete or unexpected answer. Please try again or "
        "connect another provider."
    ),
}


class CloudError(LLMError):
    def __init__(self, provider: str, code: str, retry_seconds: float | None = None) -> None:
        self.provider = provider
        self.code = code
        self.public_message = MESSAGES[code]
        self.retry_at = (
            datetime.now(UTC) + timedelta(seconds=max(0, retry_seconds))
            if retry_seconds is not None and math.isfinite(retry_seconds)
            else None
        )
        super().__init__(f"{provider}: {code}")  # Never include upstream body, key or user input.

    def to_api(self) -> dict[str, Any]:
        return {
            "provider": self.provider,
            "code": self.code,
            "message": self.public_message,
            "retry_at": self.retry_at.isoformat() if self.retry_at else None,
            "wait_known": self.retry_at is not None,
            "can_add_key": True,
        }


def retry_seconds(headers: httpx.Headers, payload: Any = None) -> float | None:
    """Trust only Retry-After or Google's structured RetryInfo; never invent a reset."""
    raw = headers.get("retry-after")
    if raw:
        try:
            seconds = float(raw)
            if math.isfinite(seconds) and 0 <= seconds <= 31_536_000:
                return seconds
        except ValueError:
            try:
                return max(0, (parsedate_to_datetime(raw) - datetime.now(UTC)).total_seconds())
            except (ValueError, TypeError, OverflowError):
                pass
    if isinstance(payload, dict):
        error = payload.get("error")
        if isinstance(error, dict):
            details = error.get("details", [])
            for item in details if isinstance(details, list) else []:
                if isinstance(item, dict) and str(item.get("@type", "")).endswith(
                    "google.rpc.RetryInfo"
                ):
                    delay = item.get("retryDelay")
                    if isinstance(delay, str) and re.fullmatch(r"\d+(?:\.\d+)?s", delay):
                        value = float(delay[:-1])
                        if value <= 31_536_000:
                            return value
    return None


def check_response(response: httpx.Response, provider: str) -> None:
    if response.status_code == 200:
        return
    try:
        data = response.json()
    except ValueError:
        data = None
    code = {
        401: "invalid_key",
        403: "invalid_key",
        404: "model_unavailable",
        429: "quota_exhausted",
        503: "queue_busy" if provider == "huggingface" else "unavailable",
    }.get(response.status_code, "unavailable")
    raise CloudError(provider, code, retry_seconds(response.headers, data))


class ProviderLLM:
    """Gemini native generateContent or Groq's OpenAI-compatible chat. No paid SDK required."""

    managed_cloud = True

    def __init__(
        self,
        *,
        provider: str,
        api_key: str,
        model: str,
        timeout: float,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        if provider not in ("gemini", "groq"):
            raise ValueError("Unsupported provider")
        if not re.fullmatch(r"[A-Za-z0-9_.:/-]{1,128}", model) or ".." in model:
            raise ValueError("Invalid model identifier")
        self.provider, self.model = provider, model
        self._key, self._timeout, self._transport = api_key, timeout, transport

    def complete(self, *, system: str, user: str) -> LLMResult:
        if self.provider == "gemini":
            url = f"https://generativelanguage.googleapis.com/v1beta/models/{self.model}:generateContent"
            headers = {"x-goog-api-key": self._key}
            body: dict[str, Any] = {
                "systemInstruction": {"parts": [{"text": system}]},
                "contents": [{"role": "user", "parts": [{"text": user}]}],
                "generationConfig": {
                    "temperature": 0.2,
                    "maxOutputTokens": 4096,
                    "responseMimeType": "application/json",
                },
            }
        else:
            url = "https://api.groq.com/openai/v1/chat/completions"
            headers = {"Authorization": f"Bearer {self._key}"}
            body = {
                "model": self.model,
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
                "response_format": {"type": "json_object"},
                "max_tokens": 1500,
                "temperature": 0.2,
            }
        try:
            with httpx.Client(
                timeout=self._timeout, transport=self._transport, follow_redirects=False
            ) as client:
                response = client.post(url, json=body, headers=headers)
            check_response(response, self.provider)
            data = response.json()
            if self.provider == "gemini":
                candidate = data["candidates"][0]
                if candidate.get("finishReason") != "STOP":
                    raise CloudError(self.provider, "bad_response")
                text = "".join(
                    p.get("text", "") for p in candidate["content"]["parts"] if not p.get("thought")
                )
            else:
                candidate = data["choices"][0]
                if candidate.get("finish_reason") != "stop":
                    raise CloudError(self.provider, "bad_response")
                text = candidate["message"]["content"]
            if not isinstance(text, str) or not text.strip() or len(text) > 20_000:
                raise CloudError(self.provider, "bad_response")
            return LLMResult(text=text, model=self.model)
        except httpx.HTTPError:
            raise CloudError(self.provider, "unavailable") from None
        except (KeyError, IndexError, ValueError, TypeError):
            raise CloudError(self.provider, "bad_response") from None


class MissingCloudLLM:
    provider, model, managed_cloud = "huggingface", "not-connected", True
    unconfigured = True

    def complete(self, *, system: str, user: str) -> LLMResult:
        raise CloudError(self.provider, "not_configured")


def space_error(payload: Any) -> CloudError:
    """Known ZeroGPU error format only. Unrecognised times remain unknown."""
    message = payload if isinstance(payload, str) else json.dumps(payload)
    lower = message.lower()
    if "quota" in lower and any(x in lower for x in ("exceeded", "exhausted", "not enough")):
        match = re.search(r"try again in\s+(\d{1,3}):(\d{2}):(\d{2})", lower)
        wait = None
        if match:
            hours, minutes, seconds = map(int, match.groups())
            if minutes < 60 and seconds < 60:
                wait = hours * 3600 + minutes * 60 + seconds
        return CloudError("huggingface", "quota_exhausted", wait)
    if "queue" in lower and any(x in lower for x in ("full", "busy")):
        return CloudError("huggingface", "queue_busy")
    return CloudError("huggingface", "unavailable")


class HuggingFaceSpaceLLM:
    """Calls the owned Gradio Space's public /respond API over HTTP+SSE.

    Space access uses the operator HF token, so quota is shared by this installation.
    No random public demo is used, no Gradio client/dependency/model runs locally.
    """

    provider, managed_cloud = "huggingface", True

    def __init__(
        self,
        *,
        url: str,
        token: str | None,
        model: str,
        timeout: float,
        transport: httpx.BaseTransport | None = None,
        app_secret: str = "",
    ) -> None:
        parsed = urlsplit(url)
        if (
            parsed.scheme != "https"
            or not parsed.hostname
            or not re.fullmatch(r"[a-z0-9][a-z0-9-]*\.hf\.space", parsed.hostname)
            or parsed.username
            or parsed.password
            or parsed.port
            or parsed.query
            or parsed.fragment
            or parsed.path not in ("", "/")
        ):
            raise ValueError("HF_SPACE_URL must be your exact https://name.hf.space origin")
        self.model, self._url, self._timeout = model, url.rstrip("/"), timeout
        self._headers = {"Authorization": f"Bearer {token}"} if token else {}
        self._transport = transport
        self._app_secret = app_secret

    def complete(self, *, system: str, user: str) -> LLMResult:
        deadline = time.monotonic() + self._timeout
        try:
            with httpx.Client(
                timeout=self._timeout,
                headers=self._headers,
                transport=self._transport,
                follow_redirects=False,
            ) as client:
                response = client.post(
                    self._url + "/gradio_api/call/respond",
                    json={"data": [json.dumps({"system": system, "user": user}), self._app_secret]},
                )
                check_response(response, self.provider)
                event_id = response.json()["event_id"]
                if not isinstance(event_id, str) or not re.fullmatch(
                    r"[A-Za-z0-9_-]{1,128}", event_id
                ):
                    raise CloudError(self.provider, "bad_response")
                event, count = "", 0
                with client.stream(
                    "GET", self._url + "/gradio_api/call/respond/" + event_id
                ) as stream:
                    if stream.status_code != 200:
                        stream.read()
                        check_response(stream, self.provider)
                    for line in stream.iter_lines():
                        count += len(line)
                        if time.monotonic() > deadline or count > 100_000:
                            raise CloudError(self.provider, "unavailable")
                        if line.startswith("event:"):
                            event = line[6:].strip()
                        elif line.startswith("data:") and event in ("complete", "error"):
                            data = json.loads(line[5:].strip())
                            if event == "error":
                                raise space_error(data)
                            text = data[0]
                            if not isinstance(text, str) or len(text) > 20_000:
                                raise CloudError(self.provider, "bad_response")
                            return LLMResult(text=text, model=self.model)
            raise CloudError(self.provider, "bad_response")
        except httpx.HTTPError:
            raise CloudError(self.provider, "unavailable") from None
        except (ValueError, KeyError, IndexError, TypeError):
            raise CloudError(self.provider, "bad_response") from None


def byok_client(settings: Settings, provider: str, key: str) -> ProviderLLM:
    return ProviderLLM(
        provider=provider,
        api_key=key,
        model=settings.gemini_model if provider == "gemini" else settings.groq_model,
        timeout=settings.cloud_timeout_seconds,
    )


def default_cloud(settings: Settings) -> HuggingFaceSpaceLLM | MissingCloudLLM:
    if not settings.hf_space_url or not settings.hf_space_app_secret or not settings.hf_token:
        return MissingCloudLLM()
    try:
        return HuggingFaceSpaceLLM(
            url=settings.hf_space_url,
            token=settings.hf_token.get_secret_value() if settings.hf_token else None,
            app_secret=settings.hf_space_app_secret.get_secret_value(),
            model=settings.hf_space_model,
            timeout=settings.cloud_timeout_seconds,
        )
    except ValueError:
        return MissingCloudLLM()
