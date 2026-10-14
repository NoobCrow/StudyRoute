"""The blueprint 19.1 demo script runs end to end (fake clock instead of real waiting)."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest

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
