"""Fee engine (blueprint section 6). Pure code: no network, no clock, no database.

Convention: all rates are BDT per 1 unit of foreign currency. A provider selling foreign
currency quotes above mid-market; the gap is the hidden margin.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal
from enum import StrEnum
from typing import Any

from app.core.crypto import hash_object
from app.engine import fx
from app.engine.money import Money, round_half_up
from app.engine.ranking import rank_results


class ChargeCode(StrEnum):
    OUR = "OUR"
    SHA = "SHA"
    BEN = "BEN"


# MT103 :71A: charge code to the ISO 20022 pacs.008 ChrgBr value (blueprint 5.2).
CHARGE_BEARER: dict[ChargeCode, str] = {
    ChargeCode.OUR: "DEBT",
    ChargeCode.SHA: "SHAR",
    ChargeCode.BEN: "CRED",
}


@dataclass(frozen=True)
class EngineParams:
    quote_ttl_seconds: int = 300
    ben_deducts_fixed_fee: bool = True


@dataclass(frozen=True)
class MidRate:
    value: Decimal
    source: str
    as_of: datetime


@dataclass(frozen=True)
class ProviderTerms:
    provider_id: str
    name: str
    margin_pct: Decimal
    fixed_fee_bdt_minor: int
    swift_fee_bdt_minor: int
    intermediary_fee_major: Decimal
    receiving_fee_major: Decimal
    supported_charge_codes: tuple[ChargeCode, ...]
    default_charge_code: ChargeCode
    eta_business_days: int

    def hashable(self) -> dict[str, Any]:
        return {
            "provider_id": self.provider_id,
            "margin_pct": str(self.margin_pct),
            "fixed_fee_bdt_minor": self.fixed_fee_bdt_minor,
            "swift_fee_bdt_minor": self.swift_fee_bdt_minor,
            "intermediary_fee_major": str(self.intermediary_fee_major),
            "receiving_fee_major": str(self.receiving_fee_major),
            "supported_charge_codes": [c.value for c in self.supported_charge_codes],
            "default_charge_code": self.default_charge_code.value,
        }


@dataclass(frozen=True)
class QuoteWarning:
    code: str
    message: str


@dataclass(frozen=True)
class ProviderResult:
    provider_id: str
    provider_name: str
    target: Money
    mid_rate: Decimal
    provider_rate: Decimal
    margin_pct: Decimal
    charge_code: ChargeCode
    requested_charge_code: ChargeCode
    fixed_fee_bdt_minor: int
    swift_fee_bdt_minor: int
    intermediary_foreign_minor: int
    receiving_foreign_minor: int
    fx_cost_bdt_minor: int
    fixed_fee_paid_by_sender_bdt_minor: int
    sender_extra_bdt_minor: int
    shortfall_foreign_minor: int
    shortfall_bdt_minor: int
    total_cost_bdt_minor: int
    cost_pct: Decimal
    parent_pays_bdt_minor: int
    eta_business_days: int
    warnings: tuple[QuoteWarning, ...]
    rank: int = 0

    @property
    def cost_pct_display(self) -> str:
        return fx.pct_display(self.cost_pct)

    @property
    def margin_pct_display(self) -> str:
        return fx.pct_display(self.margin_pct)

    @property
    def beneficiary_receives_minor(self) -> int:
        return self.target.amount_minor - self.shortfall_foreign_minor

    def _bdt(self, minor: int) -> str:
        return Money(minor, "BDT").format()

    def _foreign(self, minor: int) -> str:
        return Money(minor, self.target.currency).format()

    def display(self) -> dict[str, str]:
        return {
            "provider_rate": f"{self.provider_rate}",
            "margin_pct": f"{self.margin_pct_display}%",
            "cost_pct": f"{self.cost_pct_display}%",
            "fx_cost": self._bdt(self.fx_cost_bdt_minor),
            "fixed_fee": self._bdt(self.fixed_fee_bdt_minor),
            "swift_fee": self._bdt(self.swift_fee_bdt_minor),
            "sender_extra": self._bdt(self.sender_extra_bdt_minor),
            "shortfall_bdt": self._bdt(self.shortfall_bdt_minor),
            "total_cost": self._bdt(self.total_cost_bdt_minor),
            "parent_pays": self._bdt(self.parent_pays_bdt_minor),
            "intermediary_fee": self._foreign(self.intermediary_foreign_minor),
            "receiving_fee": self._foreign(self.receiving_foreign_minor),
            "shortfall": self._foreign(self.shortfall_foreign_minor),
            "beneficiary_receives": self._foreign(self.beneficiary_receives_minor),
        }

    def to_api_dict(self) -> dict[str, Any]:
        return {
            "rank": self.rank,
            "provider_id": self.provider_id,
            "provider_name": self.provider_name,
            "provider_rate": str(self.provider_rate),
            "margin_pct": self.margin_pct_display,
            "charge_code": self.charge_code.value,
            "requested_charge_code": self.requested_charge_code.value,
            "fees": {
                "fixed_bdt_minor": self.fixed_fee_bdt_minor,
                "swift_bdt_minor": self.swift_fee_bdt_minor,
                "intermediary_foreign_minor": self.intermediary_foreign_minor,
                "receiving_foreign_minor": self.receiving_foreign_minor,
            },
            "fixed_fee_borne_by": "sender" if self.fixed_fee_paid_by_sender_bdt_minor else "n/a",
            "breakdown": {
                "fx_cost_bdt_minor": self.fx_cost_bdt_minor,
                "fixed_fee_bdt_minor": self.fixed_fee_paid_by_sender_bdt_minor,
                "swift_fee_bdt_minor": self.swift_fee_bdt_minor,
                "sender_extra_bdt_minor": self.sender_extra_bdt_minor,
                "shortfall_bdt_minor": self.shortfall_bdt_minor,
            },
            "shortfall_foreign_minor": self.shortfall_foreign_minor,
            "beneficiary_receives_minor": self.beneficiary_receives_minor,
            "total_cost_bdt_minor": self.total_cost_bdt_minor,
            "cost_pct": self.cost_pct_display,
            "parent_pays_bdt_minor": self.parent_pays_bdt_minor,
            "eta_business_days": self.eta_business_days,
            "warnings": [{"code": w.code, "message": w.message} for w in self.warnings],
            "display": self.display(),
        }


@dataclass(frozen=True)
class Quote:
    target: Money
    purpose: str
    destination_country: str
    requested_charge_code: ChargeCode
    mid_rate: MidRate
    results: tuple[ProviderResult, ...]
    created_at: datetime
    expires_at: datetime
    input_hash: str


def _warnings(
    terms: ProviderTerms, requested: ChargeCode, applied: ChargeCode, shortfall_minor: int, ccy: str
) -> tuple[QuoteWarning, ...]:
    found: list[QuoteWarning] = []
    if applied != requested:
        found.append(
            QuoteWarning(
                "CHARGE_CODE_FALLBACK",
                f"{terms.name} does not offer {requested.value}. Quoted as {applied.value}.",
            )
        )
    if shortfall_minor > 0:
        amount = Money(shortfall_minor, ccy).format()
        found.append(
            QuoteWarning(
                "SHORTFALL_RISK",
                f"The university may receive {amount} less than the invoice, because charges "
                "are deducted from the amount. OUR avoids this modelled deduction; "
                "confirm the accepted route and charges with the university and your AD bank.",
            )
        )
    return tuple(found)


def compute_provider_result(
    *,
    target: Money,
    mid_rate: Decimal,
    terms: ProviderTerms,
    requested_charge_code: ChargeCode,
    params: EngineParams,
) -> ProviderResult:
    """Blueprint 6.2 formulas for one provider. Each money part is rounded once, half-up."""
    target.require_positive()
    ccy = target.currency
    mid = fx.to_rate(mid_rate)
    provider_rate = fx.apply_margin(mid, terms.margin_pct)

    applied = (
        requested_charge_code
        if requested_charge_code in terms.supported_charge_codes
        else terms.default_charge_code
    )
    intermediary = Money.from_major(terms.intermediary_fee_major, ccy).amount_minor
    receiving = Money.from_major(terms.receiving_fee_major, ccy).amount_minor
    deducted_fees = intermediary + receiving

    fx_cost = round_half_up(fx.foreign_to_bdt_minor(target.amount_minor, ccy, provider_rate - mid))
    fixed_paid = terms.fixed_fee_bdt_minor
    if applied is ChargeCode.OUR:
        sender_extra = round_half_up(fx.foreign_to_bdt_minor(deducted_fees, ccy, mid))
        shortfall_foreign = 0
    else:
        sender_extra = 0
        shortfall_foreign = deducted_fees
        if applied is ChargeCode.BEN and params.ben_deducts_fixed_fee:
            shortfall_foreign += round_half_up(
                fx.bdt_to_foreign_minor(terms.fixed_fee_bdt_minor, ccy, mid)
            )
            fixed_paid = 0
    shortfall_bdt = round_half_up(fx.foreign_to_bdt_minor(shortfall_foreign, ccy, mid))

    total = fx_cost + fixed_paid + terms.swift_fee_bdt_minor + sender_extra + shortfall_bdt
    base = fx.foreign_to_bdt_minor(target.amount_minor, ccy, mid)
    cost_pct = Decimal(total) / base * Decimal(100)
    parent_pays = (
        round_half_up(fx.foreign_to_bdt_minor(target.amount_minor, ccy, provider_rate))
        + fixed_paid
        + terms.swift_fee_bdt_minor
        + sender_extra
    )
    return ProviderResult(
        provider_id=terms.provider_id,
        provider_name=terms.name,
        target=target,
        mid_rate=mid,
        provider_rate=provider_rate,
        margin_pct=fx.margin_percent(provider_rate, mid),
        charge_code=applied,
        requested_charge_code=requested_charge_code,
        fixed_fee_bdt_minor=terms.fixed_fee_bdt_minor,
        swift_fee_bdt_minor=terms.swift_fee_bdt_minor,
        intermediary_foreign_minor=intermediary,
        receiving_foreign_minor=receiving,
        fx_cost_bdt_minor=fx_cost,
        fixed_fee_paid_by_sender_bdt_minor=fixed_paid,
        sender_extra_bdt_minor=sender_extra,
        shortfall_foreign_minor=shortfall_foreign,
        shortfall_bdt_minor=shortfall_bdt,
        total_cost_bdt_minor=total,
        cost_pct=cost_pct,
        parent_pays_bdt_minor=parent_pays,
        eta_business_days=terms.eta_business_days,
        warnings=_warnings(terms, requested_charge_code, applied, shortfall_foreign, ccy),
    )


def build_quote(
    *,
    target: Money,
    purpose: str,
    destination_country: str,
    charge_code: ChargeCode,
    mid_rate: MidRate,
    providers: Sequence[ProviderTerms],
    params: EngineParams,
    now: datetime,
) -> Quote:
    """Compute, rank and fingerprint a quote from every provider."""
    target.require_positive()
    results = rank_results(
        compute_provider_result(
            target=target,
            mid_rate=mid_rate.value,
            terms=terms,
            requested_charge_code=charge_code,
            params=params,
        )
        for terms in providers
    )
    input_hash = hash_object(
        {
            "target": {"amount_minor": target.amount_minor, "currency": target.currency},
            "purpose": purpose,
            "destination_country": destination_country,
            "charge_code": charge_code.value,
            "mid_rate": {
                "value": str(mid_rate.value),
                "source": mid_rate.source,
                "as_of": mid_rate.as_of.isoformat(),
            },
            "providers": [terms.hashable() for terms in providers],
            "params": {
                "quote_ttl_seconds": params.quote_ttl_seconds,
                "ben_deducts_fixed_fee": params.ben_deducts_fixed_fee,
            },
        }
    )
    return Quote(
        target=target,
        purpose=purpose,
        destination_country=destination_country,
        requested_charge_code=charge_code,
        mid_rate=mid_rate,
        results=results,
        created_at=now,
        expires_at=now + timedelta(seconds=params.quote_ttl_seconds),
        input_hash=input_hash,
    )
