"""The smart send plan as the API and the assistant present it (one code path for both)."""

from __future__ import annotations

from typing import Any

from app.domain.limits import usd_equivalent_minor
from app.domain.rules import Rules
from app.engine.cadence import CadencePlan, plan_cadence
from app.engine.money import Money
from app.engine.planner import INDICATIVE
from app.engine.quote import ChargeCode

TRADE_OFF = (
    "Sending less often costs less in fixed fees, but moves money before it is needed. "
    "Sending early can lock today's rate; StudyRoute does not predict exchange rates."
)


def build_send_plan(
    rules: Rules, *, total: Money, months: int, charge_code: str
) -> tuple[CadencePlan, dict[str, Any]]:
    """Run the engine and add the labels, the sandbox-cap flag and the honest trade-off."""
    plan = plan_cadence(
        total=total,
        months=months,
        mid_rate=rules.mid_rate(total.currency),
        providers=rules.provider_terms(),
        charge_code=ChargeCode(charge_code),
        params=rules.engine_params(),
    )
    body = plan.to_api_dict()
    cap = Money.from_major(rules.per_transaction_limit_usd, "USD").amount_minor
    for option, raw in zip(plan.options, body["options"], strict=True):
        biggest = Money(max(option.amounts_minor), total.currency)
        raw["exceeds_sandbox_cap"] = usd_equivalent_minor(rules, biggest) > cap
    body["synthetic"] = True
    body["disclaimer"] = f"Synthetic rates and fees. {INDICATIVE}"
    body["trade_off"] = TRADE_OFF
    return plan, body
