"""Synthetic FX source. There is NO live feed: every rate here is invented for the sandbox."""

from __future__ import annotations

from datetime import datetime, timedelta

from app.domain.rules import Rules
from app.engine.quote import MidRate

SYNTHETIC_SOURCE = "synthetic"


def synthetic_mid_rate(rules: Rules, currency: str, now: datetime) -> MidRate:
    """Mid-market BDT per 1 foreign unit, from config, stamped a few seconds in the past."""
    return MidRate(rules.mid_rate(currency), SYNTHETIC_SOURCE, now - timedelta(seconds=10))
