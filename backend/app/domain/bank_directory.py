"""The sandbox bank network as configuration: banks, clearing houses, rails and demo accounts.

Read once from config/bank_network.yaml. Everything in it is invented (see the file header), so
nothing here is a rule of any real bank or scheme, and nothing is marked verified.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from app.engine.interbank import RailTerms
from app.engine.money import exponent

BD = "BD"
BDT = "BDT"
AD_BANK = "AD_BANK"
CORRESPONDENT = "CORRESPONDENT"
HOST_BANK = "HOST_BANK"


@dataclass(frozen=True)
class BankInfo:
    code: str
    name: str
    country: str
    currency: str
    role: str
    provider_id: str | None = None

    def to_api(self) -> dict[str, str | None]:
        return {
            "code": self.code,
            "name": self.name,
            "country": self.country,
            "currency": self.currency,
            "role": self.role,
            "provider_id": self.provider_id,
        }


@dataclass(frozen=True)
class ClearingHouse:
    code: str
    name: str
    country: str
    currency: str


@dataclass(frozen=True)
class DemoAccount:
    key: str
    bank: str
    number: str
    holder: str
    currency: str
    opening_minor: int
    owner: str | None  # "parent", "student" or None for a third party
    label: str


@dataclass(frozen=True)
class BankDirectory:
    banks: dict[str, BankInfo]
    clearing: dict[str, ClearingHouse]
    rails: dict[str, dict[str, RailTerms]]  # currency -> rail code -> terms
    demo_accounts: tuple[DemoAccount, ...]
    slow_factor: int
    on_us_delays: tuple[int, ...]
    international_delays: tuple[int, int, int]
    nostro_major: int
    reserve_major: int

    def bank(self, code: str) -> BankInfo:
        try:
            return self.banks[code]
        except KeyError as exc:
            raise ValueError(f"Unknown bank code: {code}") from exc

    @property
    def correspondent(self) -> BankInfo:
        return next(b for b in self.banks.values() if b.role == CORRESPONDENT)

    def with_role(self, role: str) -> list[BankInfo]:
        return [b for b in self.banks.values() if b.role == role]

    def host_currencies(self) -> list[str]:
        return sorted({b.currency for b in self.with_role(HOST_BANK)})

    def clearing_house_for(self, bank: BankInfo) -> ClearingHouse | None:
        return next((c for c in self.clearing.values() if c.country == bank.country), None)

    def rails_for(self, currency: str) -> dict[str, RailTerms]:
        return self.rails.get(currency, {})

    def bank_for_provider(self, provider_id: str) -> BankInfo | None:
        return next((b for b in self.banks.values() if b.provider_id == provider_id), None)

    def opening_minor(self, currency: str, major: int) -> int:
        return major * 10 ** exponent(currency)

    def to_api(self) -> dict[str, Any]:
        return {
            "simulated": True,
            "banks": [b.to_api() for b in self.banks.values()],
            "clearing_houses": [
                {"code": c.code, "name": c.name, "country": c.country, "currency": c.currency}
                for c in self.clearing.values()
            ],
            "rails": {
                currency: [
                    {
                        "code": r.code,
                        "label": r.label,
                        "fee_fixed_minor": r.fee_fixed_minor,
                        "fee_bps": r.fee_bps,
                        "min_minor": r.min_minor,
                        "max_minor": r.max_minor,
                        "seconds": sum(r.delays),
                    }
                    for r in rails.values()
                ]
                for currency, rails in self.rails.items()
            },
            "note": "Invented banks, rails, fees and limits for the sandbox. Not any real scheme.",
        }


def _rail(code: str, currency: str, raw: dict[str, Any]) -> RailTerms:
    return RailTerms(
        code=code,
        label=str(raw["label"]),
        currency=currency,
        fee_fixed_minor=int(raw["fee_fixed_minor"]),
        fee_bps=int(raw["fee_bps"]),
        min_minor=int(raw["min_minor"]),
        max_minor=None if raw.get("max_minor") is None else int(raw["max_minor"]),
        delays=tuple(int(d) for d in raw["delays"]),
    )


def parse_directory(data: dict[str, Any]) -> BankDirectory:
    banks = {
        code: BankInfo(
            code=code,
            name=str(raw["name"]),
            country=str(raw["country"]),
            currency=str(raw["currency"]),
            role=str(raw["role"]),
            provider_id=raw.get("provider_id"),
        )
        for code, raw in data["banks"].items()
    }
    clearing = {
        code: ClearingHouse(code, str(raw["name"]), str(raw["country"]), str(raw["currency"]))
        for code, raw in data["clearing_houses"].items()
    }
    rails = {
        currency: {code: _rail(code, currency, raw) for code, raw in table.items()}
        for currency, table in data["rails"].items()
    }
    demo = tuple(
        DemoAccount(
            key=str(raw["key"]),
            bank=str(raw["bank"]),
            number=str(raw["number"]),
            holder=str(raw["holder"]),
            currency=str(raw["currency"]),
            opening_minor=int(raw["opening_minor"]),
            owner=raw.get("owner"),
            label=str(raw["label"]),
        )
        for raw in data["demo_accounts"]
    )
    timing = data["timing"]
    liquidity = data["liquidity"]
    directory = BankDirectory(
        banks=banks,
        clearing=clearing,
        rails=rails,
        demo_accounts=demo,
        slow_factor=int(timing["slow_factor"]),
        on_us_delays=tuple(int(d) for d in timing["on_us_delays"]),
        international_delays=_three(timing["international_delays"]),
        nostro_major=int(liquidity["nostro_major"]),
        reserve_major=int(liquidity["reserve_major"]),
    )
    validate(directory)
    return directory


def _three(values: list[int]) -> tuple[int, int, int]:
    if len(values) != 3:
        raise ValueError("international_delays needs exactly three numbers")
    return (int(values[0]), int(values[1]), int(values[2]))


def validate(directory: BankDirectory) -> None:
    """Fail loudly on a config that would break the ledger, instead of at the first transfer."""
    if len(directory.with_role(CORRESPONDENT)) != 1:
        raise ValueError("exactly one CORRESPONDENT bank is required")
    for bank in directory.banks.values():
        if bank.role == AD_BANK and (bank.country != BD or bank.currency != BDT):
            raise ValueError(f"{bank.code}: an AD bank is a Bangladesh BDT bank")
        if bank.role == HOST_BANK and bank.currency == BDT:
            raise ValueError(f"{bank.code}: a host bank holds a foreign currency")
    seen: set[str] = set()
    for account in directory.demo_accounts:
        bank = directory.banks.get(account.bank)
        if bank is None:
            raise ValueError(f"{account.key}: unknown bank {account.bank}")
        if bank.role == CORRESPONDENT:
            raise ValueError(f"{account.key}: customers do not bank with the correspondent")
        if bank.currency != account.currency:
            raise ValueError(f"{account.key}: {account.currency} does not match {bank.code}")
        if account.number in seen:
            raise ValueError(f"{account.key}: duplicate account number")
        seen.add(account.number)
        if account.owner not in (None, "parent", "student"):
            raise ValueError(f"{account.key}: owner must be parent, student or null")
    for bank in directory.banks.values():
        same_country = [
            b
            for b in directory.banks.values()
            if b.country == bank.country and b.role != CORRESPONDENT
        ]
        needs_clearing = bank.role != CORRESPONDENT and len(same_country) > 1
        if needs_clearing and directory.clearing_house_for(bank) is None:
            raise ValueError(f"{bank.code}: no clearing house for country {bank.country}")


def load_directory(path: Path) -> BankDirectory:
    with path.open(encoding="utf-8") as handle:
        data = yaml.safe_load(handle)
    return parse_directory(data)
