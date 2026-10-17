"""Rules configuration: YAML seeds the config_rules table, admins edit it, the engine reads it.

Nothing that can change (limits, fees, calendars, checklists, regulatory figures) is
hard-coded in Python. Rules with verified=false are shown with a yellow badge.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, replace
from datetime import date, datetime, time
from decimal import Decimal, InvalidOperation
from fnmatch import fnmatchcase
from pathlib import Path
from typing import Any

import yaml
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core import errors
from app.engine import fx
from app.engine.money import CURRENCY_EXPONENTS
from app.engine.planner import INDICATIVE, Calendar, PlannerParams, parse_weekdays
from app.engine.quote import ChargeCode, EngineParams, ProviderTerms
from app.engine.validators import IBAN_LENGTHS
from app.models import ConfigRule

HOME_COUNTRY = "BD"
GENERIC_CHECKLIST = "GENERIC"
ACCOUNT_SCHEMES = {"IBAN", "IBAN_OR_UK_DOMESTIC", "ABA_ACCOUNT", "ACCOUNT"}


@dataclass(frozen=True)
class RuleRecord:
    key: str
    value: Any
    source_url: str | None
    last_checked: str | None
    verified: bool
    kind: str
    note: str | None
    updated_by: str
    updated_at: datetime | None

    def to_api(self) -> dict[str, Any]:
        unverified = not self.verified
        return {
            "key": self.key,
            "value": self.value,
            "source_url": self.source_url,
            "last_checked": self.last_checked,
            "verified": self.verified,
            "kind": self.kind,
            "note": self.note,
            "updated_by": self.updated_by,
            "updated_at": self.updated_at.isoformat().replace("+00:00", "Z")
            if self.updated_at
            else None,
            "badge": "NOT_VERIFIED" if unverified else None,
            "indicative": INDICATIVE if unverified and self.kind == "regulatory" else None,
        }


@dataclass(frozen=True)
class Corridor:
    country: str
    name: str
    currency: str
    account_scheme: str
    host_rail: str
    featured: bool = True  # has its own hand-written rules; False means generated defaults
    restricted: bool = False  # the sandbox will not quote or save recipients for it


def flatten_rules(path: Path) -> dict[str, dict[str, Any]]:
    """Read the YAML file into {dotted.key: rule mapping}. A mapping with `value` is a rule."""
    document = yaml.safe_load(path.read_text(encoding="utf-8"))
    found: dict[str, dict[str, Any]] = {}

    def walk(node: Any, prefix: str) -> None:
        if not isinstance(node, dict):
            return
        if "value" in node:
            found[prefix] = node
            return
        for name, child in node.items():
            walk(child, f"{prefix}.{name}" if prefix else str(name))

    for name, child in document.items():
        if name != "schema_version":
            walk(child, str(name))
    return found


def sync_rules_from_file(
    session: Session, path: Path, now: datetime, *, overwrite: bool = False
) -> int:
    """Insert rules that are not in the table yet. Admin edits are never overwritten."""
    existing = {row.key: row for row in session.execute(select(ConfigRule)).scalars()}
    written = 0
    for key, rule in flatten_rules(path).items():
        row = existing.get(key)
        if row is not None and not overwrite:
            continue
        row = row or ConfigRule(key=key)
        row.value_json = rule["value"]
        row.source_url = rule.get("source_url")
        row.last_checked = rule.get("last_checked")
        row.verified = bool(rule.get("verified", False))
        row.kind = rule.get("kind", "sandbox_design")
        row.note = rule.get("note")
        row.updated_by = "system"
        row.updated_at = now
        session.add(row)
        written += 1
    session.flush()
    return written


def _record(row: ConfigRule) -> RuleRecord:
    return RuleRecord(
        row.key, row.value_json, row.source_url, row.last_checked, row.verified,
        row.kind, row.note, row.updated_by, row.updated_at,
    )  # fmt: skip


def load_rules(session: Session) -> Rules:
    rows = session.execute(select(ConfigRule)).scalars().all()
    return Rules({row.key: _record(row) for row in rows})


class Rules:
    """Typed, read-only view over the rule table."""

    def __init__(self, records: Mapping[str, RuleRecord]) -> None:
        self._records = dict(records)

    def record(self, key: str) -> RuleRecord:
        try:
            return self._records[key]
        except KeyError as exc:
            raise errors.ValidationFailed(f"Unknown rule: {key}") from exc

    def raw(self, key: str) -> Any:
        return self.record(key).value

    def records_with_prefix(self, prefix: str) -> dict[str, RuleRecord]:
        """The rules whose key starts with `prefix` (for example `student_costs.`), by the rest."""
        return {
            key[len(prefix) :]: record
            for key, record in sorted(self._records.items())
            if key.startswith(prefix)
        }

    def to_api(self) -> list[dict[str, Any]]:
        return [self._records[key].to_api() for key in sorted(self._records)]

    # --- engine parameters -------------------------------------------------------------
    @property
    def quote_ttl_seconds(self) -> int:
        return int(self.raw("engine.quote_ttl_seconds"))

    @property
    def mfa_proof_ttl_seconds(self) -> int:
        return int(self.raw("engine.mfa_proof_ttl_seconds"))

    @property
    def idempotency_ttl_hours(self) -> int:
        return int(self.raw("engine.idempotency_ttl_hours"))

    def engine_params(self) -> EngineParams:
        return EngineParams(
            quote_ttl_seconds=self.quote_ttl_seconds,
            ben_deducts_fixed_fee=bool(self.raw("engine.ben_deducts_fixed_fee")),
        )

    def planner_params(self) -> PlannerParams:
        hours, minutes = str(self.raw("engine.bank_cutoff_local")).split(":")
        return PlannerParams(
            settlement_business_days=int(self.raw("engine.settlement_business_days")),
            buffer_days=int(self.raw("engine.planner_buffer_days")),
            cutoff=time(int(hours), int(minutes)),
        )

    # --- limits and compliance ---------------------------------------------------------
    @property
    def per_transaction_limit_usd(self) -> int:
        return int(self.raw("limits.per_transaction_usd_equivalent"))

    @property
    def daily_limit_usd(self) -> int:
        return int(self.raw("limits.daily_usd_equivalent"))

    @property
    def sanctions_token(self) -> str:
        return str(self.raw("compliance.sanctions_test_token"))

    @property
    def fail_token(self) -> str:
        return str(self.raw("compliance.fail_test_token"))

    @property
    def slow_token(self) -> str:
        return str(self.raw("compliance.slow_test_token"))

    @property
    def review_large_usd(self) -> int:
        return int(self.raw("review.large_amount_usd_equivalent"))

    @property
    def review_split_window_days(self) -> int:
        return int(self.raw("review.split_window_days"))

    @property
    def review_split_min_payments(self) -> int:
        return int(self.raw("review.split_min_payments"))

    @property
    def review_test_token(self) -> str:
        return str(self.raw("review.review_test_token"))

    @property
    def review_bank_authorizes_all(self) -> bool:
        return bool(self.raw("review.bank_authorizes_every_payment"))

    @property
    def review_target_hours(self) -> int:
        return int(self.raw("review.decision_target_hours"))

    @property
    def review_reminder_hours(self) -> int:
        return int(self.raw("review.reminder_cooldown_hours"))

    @property
    def review_reason_codes(self) -> list[str]:
        return [str(item) for item in self.raw("review.decline_reason_codes")]

    @property
    def kyc_required_documents(self) -> list[str]:
        return [str(item) for item in self.raw("kyc.required_documents")]

    @property
    def kyc_review_seconds(self) -> int:
        return int(self.raw("kyc.mock_review_seconds"))

    # --- providers, rates, corridors ---------------------------------------------------
    def provider_terms(self) -> list[ProviderTerms]:
        keys = sorted(k for k in self._records if k.startswith("providers."))
        return [_parse_provider(k.split(".", 1)[1], self._records[k].value) for k in keys]

    def provider_ids(self) -> list[str]:
        return [t.provider_id for t in self.provider_terms()]

    def mid_rate(self, currency: str) -> Decimal:
        """A hand-written fx.mid_rates rule wins; otherwise the generated synthetic table."""
        record = self._records.get(f"fx.mid_rates.{currency}")
        if record is not None:
            return fx.to_rate(record.value)
        generated = self._records.get("countries.rates")
        if generated is not None and currency in generated.value:
            return fx.to_rate(generated.value[currency])
        raise errors.ValidationFailed(f"No synthetic mid-market rate for {currency}.")

    def corridors(self) -> dict[str, Corridor]:
        """Hand-written corridors first, then every other country by name (generated defaults)."""
        found: dict[str, Corridor] = {}
        for key in sorted(k for k in self._records if k.startswith("corridors.")):
            country = key.split(".", 1)[1]
            v = self._records[key].value
            found[country] = Corridor(
                country, v["name"], v["currency"], v["account_scheme"], v["host_rail"]
            )
        for country, row in sorted(self._directory().items(), key=lambda item: item[1]["name"]):
            if country not in found:
                found[country] = _generated_corridor(country, row)
        blocked = self.restricted_countries()
        return {c: replace(v, restricted=c in blocked) for c, v in found.items()}

    def restricted_countries(self) -> set[str]:
        record = self._records.get("countries.restricted")
        return {str(code) for code in record.value} if record else set()

    def open_corridor(self, country: str) -> Corridor:
        """The corridor, or an error if the sandbox does not quote payments to it."""
        corridor = self.corridor(country)
        if corridor.restricted:
            raise errors.ValidationFailed(
                f"The sandbox does not quote payments to {corridor.name}, because banks often "
                "refuse that destination. Confirm with your AD bank."
            )
        return corridor

    def _directory(self) -> Mapping[str, Mapping[str, Any]]:
        record = self._records.get("countries.directory")
        return record.value if record else {}

    def corridor(self, country: str) -> Corridor:
        try:
            return self.corridors()[country]
        except KeyError as exc:
            raise errors.ValidationFailed(f"Unsupported destination country: {country}") from exc

    def supported_currencies(self) -> set[str]:
        return {c.currency for c in self.corridors().values()}

    # --- calendars and checklists ------------------------------------------------------
    def calendar(self, country: str) -> Calendar:
        weekend_rule = self._records.get(f"calendars.weekend.{country}")
        if weekend_rule is not None:
            weekend = parse_weekdays(weekend_rule.value)
        else:
            row = self._directory().get(country)
            if row is None:
                raise errors.ValidationFailed(f"Unsupported destination country: {country}")
            weekend = parse_weekdays(row["weekend"])
        holiday_rule = self._records.get(f"calendars.holidays.{country}")
        raw_holidays = holiday_rule.value if holiday_rule is not None else {}
        holidays = {date.fromisoformat(day): str(name) for day, name in raw_holidays.items()}
        return Calendar(country, weekend, holidays)

    def calendars(self, host_country: str) -> list[Calendar]:
        self.corridor(host_country)
        return [self.calendar(HOME_COUNTRY), self.calendar(host_country)]

    def checklist(self, country: str, purpose: str) -> dict[str, Any]:
        corridor = self.corridor(country)
        generic = f"checklists.{GENERIC_CHECKLIST}_{purpose}"
        key = f"checklists.{country}_{purpose}"
        own = key in self._records
        if not own and generic not in self._records:
            raise errors.ValidationFailed(f"No checklist for {country} / {purpose}.")
        rule = self._records[key if own else generic]
        labels = self.raw("checklist_labels")
        items = [
            {"key": item, "label": labels[item]["label"], "hint": labels[item]["hint"]}
            for item in rule.value
        ]
        note = rule.note
        if not own:
            note = (
                f"A general list: documents specific to {corridor.name} are not loaded. "
                f"{rule.note or INDICATIVE}"
            )
        return {
            "country": country,
            "purpose": purpose,
            "items": items,
            "verified": rule.verified,
            "source_url": rule.source_url,
            "last_checked": rule.last_checked,
            "note": note,
            "indicative": INDICATIVE,
        }


def _generated_corridor(country: str, row: Mapping[str, Any]) -> Corridor:
    scheme = "IBAN" if country in IBAN_LENGTHS else "ACCOUNT"
    rail = f"Local banking system of {row['name']} (named only: the sandbox does not simulate it)"
    return Corridor(country, row["name"], row["currency"], scheme, rail, featured=False)


def _parse_provider(provider_id: str, value: Mapping[str, Any]) -> ProviderTerms:
    return ProviderTerms(
        provider_id=provider_id,
        name=str(value["name"]),
        margin_pct=Decimal(str(value["margin_pct"])),
        fixed_fee_bdt_minor=int(value["fixed_fee_bdt_minor"]),
        swift_fee_bdt_minor=int(value["swift_fee_bdt_minor"]),
        intermediary_fee_major=Decimal(str(value["intermediary_fee_major"])),
        receiving_fee_major=Decimal(str(value["receiving_fee_major"])),
        supported_charge_codes=tuple(ChargeCode(c) for c in value["supported_charge_codes"]),
        default_charge_code=ChargeCode(value["default_charge_code"]),
        eta_business_days=int(value["eta_business_days"]),
    )


# --- admin updates ---------------------------------------------------------------------
def _bad(message: str) -> errors.ApiError:
    return errors.ValidationFailed(message)


def _int_between(low: int, high: int) -> Any:
    def check(value: Any) -> None:
        if isinstance(value, bool) or not isinstance(value, int) or not low <= value <= high:
            raise _bad(f"Value must be a whole number from {low} to {high}.")

    return check


def _check_bool(value: Any) -> None:
    if not isinstance(value, bool):
        raise _bad("Value must be true or false.")


def _check_cutoff(value: Any) -> None:
    try:
        hours, minutes = str(value).split(":")
        time(int(hours), int(minutes))
    except ValueError as exc:
        raise _bad("Value must look like 15:00.") from exc


def _check_token(value: Any) -> None:
    if not isinstance(value, str) or not 3 <= len(value) <= 40:
        raise _bad("Value must be text of 3 to 40 characters.")


def _check_str_list(value: Any) -> None:
    if not isinstance(value, list) or not value or not all(isinstance(v, str) for v in value):
        raise _bad("Value must be a non-empty list of text items.")


def _check_weekdays(value: Any) -> None:
    _check_str_list(value)
    try:
        parse_weekdays(value)
    except ValueError as exc:
        raise _bad(str(exc)) from exc


def _check_holidays(value: Any) -> None:
    if not isinstance(value, dict):
        raise _bad("Value must map ISO dates to holiday names.")
    for day, name in value.items():
        try:
            date.fromisoformat(day)
        except (TypeError, ValueError) as exc:
            raise _bad(f"Not an ISO date: {day}") from exc
        if not isinstance(name, str) or not name:
            raise _bad("Holiday names must be text.")


def _check_rate(value: Any) -> None:
    try:
        fx.to_rate(Decimal(str(value)))
    except (InvalidOperation, ValueError, TypeError, errors.ApiError, Exception) as exc:
        raise _bad("Value must be a positive decimal rate.") from exc


def _check_provider(value: Any) -> None:
    try:
        _parse_provider("check", value)
    except (KeyError, ValueError, TypeError, InvalidOperation) as exc:
        raise _bad("Provider terms are incomplete or malformed.") from exc


def _check_corridor(value: Any) -> None:
    ok = (
        isinstance(value, dict)
        and {"name", "currency", "account_scheme", "host_rail"} <= value.keys()
        and value["currency"] in CURRENCY_EXPONENTS
        and value["account_scheme"] in ACCOUNT_SCHEMES
    )
    if not ok:
        raise _bad("Corridor needs name, currency, account_scheme and host_rail.")


def _check_directory(value: Any) -> None:
    ok = isinstance(value, dict) and all(
        isinstance(code, str)
        and len(code) == 2
        and isinstance(row, dict)
        and {"name", "currency", "weekend"} <= row.keys()
        and row["currency"] in CURRENCY_EXPONENTS
        for code, row in value.items()
    )
    if not ok:
        raise _bad("Each country needs a 2-letter code, a name, a known currency and a weekend.")


def _check_rate_table(value: Any) -> None:
    if not isinstance(value, dict) or not all(c in CURRENCY_EXPONENTS for c in value):
        raise _bad("Rates must be a table of known currency codes.")
    for rate in value.values():
        _check_rate(rate)


def _check_country_codes(value: Any) -> None:
    ok = isinstance(value, list) and all(
        isinstance(code, str) and len(code) == 2 and code.isupper() for code in value
    )
    if not ok:
        raise _bad("Give a list of 2-letter country codes, such as KP.")


def _check_labels(value: Any) -> None:
    ok = isinstance(value, dict) and all(
        isinstance(v, dict) and {"label", "hint"} <= v.keys() for v in value.values()
    )
    if not ok:
        raise _bad("Each checklist label needs a label and a hint.")


_VALIDATORS: list[tuple[str, Any]] = [
    ("engine.quote_ttl_seconds", _int_between(30, 3600)),
    ("engine.mfa_proof_ttl_seconds", _int_between(30, 900)),
    ("engine.settlement_business_days", _int_between(0, 10)),
    ("engine.planner_buffer_days", _int_between(0, 10)),
    ("engine.idempotency_ttl_hours", _int_between(1, 168)),
    ("engine.bank_cutoff_local", _check_cutoff),
    ("engine.ben_deducts_fixed_fee", _check_bool),
    ("limits.*", _int_between(1, 10_000_000)),
    ("compliance.*", _check_token),
    ("kyc.required_documents", _check_str_list),
    ("kyc.mock_review_seconds", _int_between(0, 3600)),
    ("calendars.weekend.*", _check_weekdays),
    ("calendars.holidays.*", _check_holidays),
    ("fx.mid_rates.*", _check_rate),
    ("fx.history_days", _int_between(7, 365)),
    ("providers.*", _check_provider),
    ("corridors.*", _check_corridor),
    ("countries.directory", _check_directory),
    ("countries.rates", _check_rate_table),
    ("countries.restricted", _check_country_codes),
    ("checklist_labels", _check_labels),
    ("checklists.*", _check_str_list),
]


def validate_rule_value(key: str, value: Any, previous: Any) -> None:
    for pattern, check in _VALIDATORS:
        if fnmatchcase(key, pattern):
            check(value)
            return
    if previous is not None and type(value) is not type(previous):
        raise _bad("Value must keep the same type as the current value.")


def update_rule(
    session: Session,
    *,
    key: str,
    value: Any,
    source_url: str | None,
    verified: bool,
    reason: str,
    updated_by: str,
    now: datetime,
) -> tuple[RuleRecord, RuleRecord]:
    """Change one rule. Returns (before, after) so the caller can write the audit event."""
    row = session.get(ConfigRule, key)
    if row is None:
        raise _bad(f"Unknown rule: {key}")
    if len(reason.strip()) < 3:
        raise _bad("A reason for the change is required.")
    validate_rule_value(key, value, row.value_json)
    new_source = source_url if source_url is not None else row.source_url
    if verified and row.kind == "regulatory" and not new_source:
        raise _bad("A regulatory rule can only be marked verified with a source URL.")
    before = _record(row)
    row.value_json = value
    row.source_url = new_source
    row.verified = verified
    row.last_checked = now.date().isoformat()
    row.updated_by = updated_by
    row.updated_at = now
    session.flush()
    return before, _record(row)
