"""Mock sanctions screening and simulator scenarios, driven by tokens in config."""

from __future__ import annotations

from app.domain.rules import Rules
from app.providers.base import Scenario


def is_sanctions_hit(rules: Rules, name: str) -> bool:
    return rules.sanctions_token.lower() in name.lower()


def scenario_for(rules: Rules, recipient_name: str) -> Scenario:
    lowered = recipient_name.lower()
    if rules.fail_token.lower() in lowered:
        return Scenario.FAIL
    if rules.slow_token.lower() in lowered:
        return Scenario.SLOW
    return Scenario.NORMAL
