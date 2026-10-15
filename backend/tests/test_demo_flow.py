"""The blueprint 19.1 demo script runs end to end (fake clock instead of real waiting)."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest

from app.ai.nlu.runtime import load_reader
from app.scripts.demo_flow import DemoFlow
from tests.helpers import MFA_CODE, PASSWORD, World


@pytest.fixture
def world(tmp_path: Path) -> Iterator[World]:
    """The demo now includes the sandbox bank network, so seed it."""
    instance = World(tmp_path, bank_network=True)
    yield instance
    instance.close()


def test_the_demo_script_passes_every_check(world: World) -> None:
    def wait(seconds: float) -> None:
        world.clock.advance(seconds)
        world.ctx.worker.tick()

    lines: list[str] = []
    flow = DemoFlow(world.client, password=PASSWORD, mfa_code=MFA_CODE, wait=wait, say=lines.append)
    failures = flow.run()
    assert failures == [], "\n".join(lines)
    transcript = "\n".join(lines)
    assert "SETTLED" in transcript
    assert "chain verifies: PASS" in transcript
    assert "[13] Smart escrow" in transcript and "[14] Audit log" in transcript
    assert "locked in the escrow contract" in transcript
    assert "anchored on the chain and the database matches it" in transcript


def test_the_demo_passes_with_the_real_rate_limits_switched_on(tmp_path: Path) -> None:
    """A real server allows 10 sign-in and MFA requests a minute per address. The demo makes more
    than that, so it must wait as the server asks. (Tests usually switch the limits off, which hid
    this until the demo ran against the real stack.)"""
    instance = World(tmp_path, bank_network=True, rate_limit_enabled=True)
    try:

        def wait(seconds: float) -> None:
            instance.clock.advance(seconds)
            instance.ctx.worker.tick()

        lines: list[str] = []
        flow = DemoFlow(
            instance.client, password=PASSWORD, mfa_code=MFA_CODE, wait=wait, say=lines.append
        )
        failures = flow.run()
        transcript = "\n".join(lines)
        assert failures == [], transcript
        assert "rate limit: waiting" in transcript, "the limit really was hit and waited out"
        assert "[14] Audit log" in transcript and "chain verifies: PASS" in transcript
    finally:
        instance.close()


def test_the_demo_passes_with_the_trained_reader_switched_on(tmp_path: Path) -> None:
    """The same fourteen steps, with the model reading the messages instead of the fixed rules."""
    if load_reader("auto") is None:
        pytest.skip("the trained reader is not available")
    instance = World(tmp_path, bank_network=True, nlu_mode="auto", dialogue_mode="auto")
    try:

        def wait(seconds: float) -> None:
            instance.clock.advance(seconds)
            instance.ctx.worker.tick()

        lines: list[str] = []
        flow = DemoFlow(
            instance.client, password=PASSWORD, mfa_code=MFA_CODE, wait=wait, say=lines.append
        )
        failures = flow.run()
        transcript = "\n".join(lines)
        assert failures == [], transcript
        assert "the trained reader read 'ten thousand pounds'" in transcript
        assert "Reader studyroute-nlu" in transcript
    finally:
        instance.close()
