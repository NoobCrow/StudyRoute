"""The AI readiness check: template mode, a healthy model, and every way it can fail."""

from __future__ import annotations

from app.ai.llm import LLMError
from app.ai.orchestrator import Orchestrator
from app.scripts.check_ai import run_check
from tests.helpers import World
from tests.test_ai_llm_mode import FakeLLM, good


def check(world: World) -> tuple[bool, str]:
    lines: list[str] = []
    ok = run_check(world.ctx, lines.append)
    return ok, "\n".join(lines)


def test_template_mode_without_a_key_is_healthy_and_says_how_to_add_one(world: World) -> None:
    ok, text = check(world)
    assert ok
    assert "assistant mode:      template" in text
    assert "injection attempt:   refused (policy_blocked)" in text
    assert "LLM_API_KEY" in text


def test_a_working_model_passes_with_the_pinned_model_version(world: World) -> None:
    fake = FakeLLM(good("Provider B costs 1.58% of the amount."))
    world.ctx.assistant = Orchestrator(world.ctx, fake)
    ok, text = check(world)
    assert ok, text
    assert "model version:       fake-model-1" in text
    assert "guard status:        passed" in text
    assert len(fake.calls) == 1, "the injection attempt must never reach the model"


def test_a_model_that_is_down_fails_the_check(world: World) -> None:
    world.ctx.assistant = Orchestrator(world.ctx, FakeLLM(LLMError("boom")))
    ok, text = check(world)
    assert not ok
    assert text.rstrip().endswith("FAIL")


def test_a_model_that_invents_a_number_fails_the_check(world: World) -> None:
    world.ctx.assistant = Orchestrator(world.ctx, FakeLLM(good("Provider B costs 3.99%.")))
    ok, text = check(world)
    assert not ok
    assert "template_fallback" in text


def test_a_requested_but_unavailable_model_is_reported_as_misconfiguration(
    world: World,
) -> None:
    world.ctx.settings.llm_provider = "openai_compatible"
    ok, text = check(world)
    assert not ok
    assert "LLM_BASE_URL" in text
    assert "template mode" in text
