"""Currency-drop stress test: what a payment would cost if the taka weakened before it is sent.

A what-if on the synthetic rates, never a forecast. The quote is priced again by the same fee
engine with the foreign currency X% more expensive in taka, for the same provider, so every figure
is the engine's. Fixed fees in taka do not move with the rate; the rate-driven part does. Read-only:
nothing is created or changed, so no audit event is written.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

from app.core import errors
from app.domain.rules import Rules
from app.engine import fx
from app.engine.money import Money
from app.engine.planner import INDICATIVE
from app.engine.quote import ChargeCode, MidRate, ProviderResult, build_quote

DEFAULT_DROPS: tuple[Decimal, ...] = (Decimal(5), Decimal(10), Decimal(15), Decimal(20))
MAX_SCENARIOS = 6
MAX_DROP = Decimal(50)
_RATE_STEP = Decimal("0.000001")
NOTE = "A what-if on synthetic rates, not a forecast. " + INDICATIVE


def parse_drops(raw: str | None) -> tuple[Decimal, ...]:
    """'5,10,15' -> Decimals, ascending and unique. Refuses anything outside 1 to 50 percent."""
    if not raw:
        return DEFAULT_DROPS
    try:
        values = {Decimal(part.strip()) for part in raw.split(",") if part.strip()}
    except ArithmeticError as exc:
        raise errors.ValidationFailed("Drops must be numbers such as 5,10,15.") from exc
    if not values or len(values) > MAX_SCENARIOS:
        raise errors.ValidationFailed(f"Give between 1 and {MAX_SCENARIOS} drops.")
    if any(not Decimal(1) <= v <= MAX_DROP for v in values):
        raise errors.ValidationFailed("Each drop must be between 1 and 50 percent.")
    return tuple(sorted(values))


def _pct(value: Decimal) -> str:
    return f"{value.normalize():f}%"


def _price(
    quote: dict[str, Any], rules: Rules, mid: Decimal, now: datetime, provider_id: str
) -> ProviderResult:
    result = build_quote(
        target=Money(quote["target"]["amount_minor"], quote["target"]["currency"]),
        purpose=quote["purpose"],
        destination_country=quote["destination_country"],
        charge_code=ChargeCode(quote["charge_code"]),
        mid_rate=MidRate(mid, quote["mid_rate"]["source"], now),
        providers=rules.provider_terms(),
        params=rules.engine_params(),
        now=now,
    )
    return next(r for r in result.results if r.provider_id == provider_id)


def _default_provider(quote: dict[str, Any]) -> str:
    fit = quote.get("deadline_fit")
    if fit and fit.get("best_in_time"):
        return str(fit["best_in_time"])
    return str(min(quote["results"], key=lambda r: r["rank"])["provider_id"])


def stress_quote(
    rules: Rules,
    quote: dict[str, Any],
    *,
    drops: Sequence[Decimal] = DEFAULT_DROPS,
    provider_id: str | None = None,
) -> dict[str, Any]:
    """Price the quote again at each drop, for one provider (default: the one the plan proposes)."""
    chosen = provider_id or _default_provider(quote)
    if chosen not in {r["provider_id"] for r in quote["results"]}:
        raise errors.ValidationFailed("That provider is not on this quote.")
    base_mid = Decimal(quote["mid_rate"]["value"])
    now = datetime.fromisoformat(quote["created_at"])
    baseline = _price(quote, rules, base_mid, now, chosen)
    rows = []
    for drop in drops:
        mid = (base_mid * (Decimal(1) + drop / Decimal(100))).quantize(
            _RATE_STEP, rounding=ROUND_HALF_UP
        )
        stressed = _price(quote, rules, mid, now, chosen)
        extra = stressed.parent_pays_bdt_minor - baseline.parent_pays_bdt_minor
        extra_pct = (Decimal(extra) * 100 / Decimal(baseline.parent_pays_bdt_minor)).quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP
        )
        rows.append(
            {
                "drop_pct": _pct(drop),
                "mid_rate": str(mid),
                "provider_rate": str(stressed.provider_rate),
                "parent_pays_bdt_minor": stressed.parent_pays_bdt_minor,
                "extra_bdt_minor": extra,
                "extra_pct": fx.pct_display(extra_pct),
                "display": {
                    "parent_pays": Money(stressed.parent_pays_bdt_minor, "BDT").format(),
                    "extra": Money(extra, "BDT").format(),
                    "extra_pct": f"{fx.pct_display(extra_pct)}%",
                    "provider_rate": f"{stressed.provider_rate}",
                },
            }
        )
    return {
        "quote_id": quote["quote_id"],
        "provider_id": chosen,
        "provider_name": baseline.provider_name,
        "target": quote["target"],
        "baseline": {
            "mid_rate": str(base_mid),
            "parent_pays_bdt_minor": baseline.parent_pays_bdt_minor,
            "display": {
                "parent_pays": Money(baseline.parent_pays_bdt_minor, "BDT").format(),
                "provider_rate": f"{baseline.provider_rate}",
            },
        },
        "scenarios": rows,
        "assumption": (
            f"The taka weakens so that each {quote['target']['currency']} costs the given "
            "percentage more taka; fixed fees in taka stay as they are."
        ),
        "synthetic": True,
        "note": NOTE,
    }
