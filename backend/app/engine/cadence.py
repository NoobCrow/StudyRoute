"""Smart send plan: what the same money costs sent monthly, quarterly, per term or at once.

Pure code, like the rest of the engine. Fixed and SWIFT fees are paid on every transfer while the
FX margin scales with the amount, so the number of transfers changes the real cost. For each
cadence the engine splits the total evenly, prices every transfer with each provider using the
blueprint 6.2 formulas, and keeps the provider with the lowest total, never one that would leave
the beneficiary short while another would not.

The engine does not predict exchange rates: sending early can lock today's rate but moves money
before it is needed. That trade-off is stated, not priced.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from app.engine import fx
from app.engine.money import InvalidAmount, Money
from app.engine.quote import (
    ChargeCode,
    EngineParams,
    ProviderResult,
    ProviderTerms,
    compute_provider_result,
)

MAX_MONTHS = 60

# (key, label, months covered by one transfer). The last one sends everything at once.
_CADENCES: tuple[tuple[str, str, int | None], ...] = (
    ("monthly", "Every month", 1),
    ("quarterly", "Every three months", 3),
    ("termly", "Every six months", 6),
    ("upfront", "All at once", None),
)


def split_evenly(total_minor: int, parts: int) -> tuple[int, ...]:
    """Split minor units into `parts` amounts that differ by at most one and sum to the total."""
    if parts < 1:
        raise ValueError("parts must be at least 1")
    base, remainder = divmod(total_minor, parts)
    return tuple(base + 1 if index < remainder else base for index in range(parts))


@dataclass(frozen=True)
class CadenceOption:
    key: str
    label: str
    transfers: int
    amounts_minor: tuple[int, ...]
    currency: str
    provider_id: str
    provider_name: str
    charge_code: ChargeCode
    total_cost_bdt_minor: int
    parent_pays_bdt_minor: int
    avg_cost_pct: Decimal
    shortfall_foreign_minor: int
    saving_vs_monthly_bdt_minor: int

    def to_api_dict(self) -> dict[str, Any]:
        per_transfer = Money(self.amounts_minor[0], self.currency)
        return {
            "key": self.key,
            "label": self.label,
            "transfers": self.transfers,
            "per_transfer": per_transfer.to_dict(),
            "provider_id": self.provider_id,
            "provider_name": self.provider_name,
            "charge_code": self.charge_code.value,
            "total_cost_bdt_minor": self.total_cost_bdt_minor,
            "parent_pays_bdt_minor": self.parent_pays_bdt_minor,
            "avg_cost_pct": fx.pct_display(self.avg_cost_pct),
            "shortfall_foreign_minor": self.shortfall_foreign_minor,
            "saving_vs_monthly_bdt_minor": self.saving_vs_monthly_bdt_minor,
            "display": {
                "per_transfer": per_transfer.format(),
                "total_cost": Money(self.total_cost_bdt_minor, "BDT").format(),
                "parent_pays": Money(self.parent_pays_bdt_minor, "BDT").format(),
                "avg_cost_pct": f"{fx.pct_display(self.avg_cost_pct)}%",
                "saving_vs_monthly": Money(self.saving_vs_monthly_bdt_minor, "BDT").format(),
            },
        }


@dataclass(frozen=True)
class CadencePlan:
    total: Money
    months: int
    options: tuple[CadenceOption, ...]
    cheapest_key: str

    def to_api_dict(self) -> dict[str, Any]:
        return {
            "total": self.total.to_dict(),
            "months": self.months,
            "cheapest_key": self.cheapest_key,
            "options": [o.to_api_dict() for o in self.options],
        }


def _transfer_counts(months: int) -> list[tuple[str, str, int]]:
    """The cadences for this many months, each with its number of transfers, without repeats."""
    seen: set[int] = set()
    counts: list[tuple[str, str, int]] = []
    for key, label, span in _CADENCES:
        transfers = 1 if span is None else -(-months // span)  # ceiling division
        if transfers in seen:
            continue
        seen.add(transfers)
        counts.append((key, label, transfers))
    return counts


def _price(
    amounts: Sequence[int],
    currency: str,
    mid_rate: Decimal,
    terms: ProviderTerms,
    charge_code: ChargeCode,
    params: EngineParams,
) -> list[ProviderResult]:
    return [
        compute_provider_result(
            target=Money(amount, currency),
            mid_rate=mid_rate,
            terms=terms,
            requested_charge_code=charge_code,
            params=params,
        )
        for amount in amounts
    ]


def _best_provider(
    amounts: tuple[int, ...],
    currency: str,
    mid_rate: Decimal,
    providers: Sequence[ProviderTerms],
    charge_code: ChargeCode,
    params: EngineParams,
) -> tuple[ProviderTerms, list[ProviderResult]]:
    """Lowest total cost; a provider that leaves the beneficiary short only wins if all do."""
    priced = [
        (terms, _price(amounts, currency, mid_rate, terms, charge_code, params))
        for terms in providers
    ]

    def key(item: tuple[ProviderTerms, list[ProviderResult]]) -> tuple[bool, int, str]:
        terms, results = item
        short = sum(r.shortfall_foreign_minor for r in results) > 0
        return (short, sum(r.total_cost_bdt_minor for r in results), terms.provider_id)

    return min(priced, key=key)


def plan_cadence(
    *,
    total: Money,
    months: int,
    mid_rate: Decimal,
    providers: Sequence[ProviderTerms],
    charge_code: ChargeCode,
    params: EngineParams,
) -> CadencePlan:
    total.require_positive()
    if not 1 <= months <= MAX_MONTHS:
        raise ValueError(f"months must be between 1 and {MAX_MONTHS}")
    if not providers:
        raise ValueError("at least one provider is needed")
    mid = fx.to_rate(mid_rate)
    drafts: list[tuple[str, str, tuple[int, ...], ProviderTerms, list[ProviderResult]]] = []
    for key, label, transfers in _transfer_counts(months):
        amounts = split_evenly(total.amount_minor, transfers)
        if min(amounts) <= 0:
            raise InvalidAmount("The total is too small to split into that many transfers.")
        terms, results = _best_provider(
            amounts, total.currency, mid, providers, charge_code, params
        )
        drafts.append((key, label, amounts, terms, results))

    monthly_cost = sum(r.total_cost_bdt_minor for r in drafts[0][4])
    base = sum(fx.foreign_to_bdt_minor(a, total.currency, mid) for a in drafts[0][2])
    options: list[CadenceOption] = []
    for key, label, amounts, terms, results in drafts:
        cost = sum(r.total_cost_bdt_minor for r in results)
        options.append(
            CadenceOption(
                key=key,
                label=label,
                transfers=len(amounts),
                amounts_minor=amounts,
                currency=total.currency,
                provider_id=terms.provider_id,
                provider_name=terms.name,
                charge_code=results[0].charge_code,
                total_cost_bdt_minor=cost,
                parent_pays_bdt_minor=sum(r.parent_pays_bdt_minor for r in results),
                avg_cost_pct=Decimal(cost) / base * Decimal(100),
                shortfall_foreign_minor=sum(r.shortfall_foreign_minor for r in results),
                saving_vs_monthly_bdt_minor=monthly_cost - cost,
            )
        )
    cheapest = min(options, key=lambda o: (o.total_cost_bdt_minor, o.transfers))
    return CadencePlan(total, months, tuple(options), cheapest.key)
