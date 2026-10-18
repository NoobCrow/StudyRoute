"""Builds the provider adapters from the current rules (so config edits take effect)."""

from __future__ import annotations

from app.core.config import Settings
from app.domain.rules import Rules
from app.providers.base import ProviderAdapter, SimulatorTiming, SyntheticProvider


class UnknownProvider(KeyError):
    pass


class ProviderRegistry:
    def __init__(self, settings: Settings) -> None:
        self._timing = SimulatorTiming(
            settle_delay_seconds=settings.settle_delay_seconds,
            slow_delay_seconds=settings.slow_settle_delay_seconds,
        )

    def adapters(self, rules: Rules) -> list[ProviderAdapter]:
        return [SyntheticProvider(t, self._timing) for t in rules.provider_terms()]

    def get(self, rules: Rules, provider_id: str) -> ProviderAdapter:
        for adapter in self.adapters(rules):
            if adapter.provider_id == provider_id:
                return adapter
        raise UnknownProvider(provider_id)
