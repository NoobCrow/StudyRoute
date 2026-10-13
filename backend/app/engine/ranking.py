"""Rank provider results by true total cost percentage, cheapest first."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import replace
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.engine.quote import ProviderResult


def rank_results(results: Iterable[ProviderResult]) -> tuple[ProviderResult, ...]:
    """Order by cost_pct, then by what the parent pays, then by provider id (deterministic)."""
    ordered = sorted(results, key=lambda r: (r.cost_pct, r.parent_pays_bdt_minor, r.provider_id))
    return tuple(replace(result, rank=position) for position, result in enumerate(ordered, 1))
