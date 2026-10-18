"""F21 student budget and F22 arrival guide: read-only help for a student abroad.

Both are built from config (`student_costs.*`, `arrival_guide.*`, `arrival_labels`), never from
code, and every one of those rules is marked not verified, so the answers say so. The cost
figures are invented for the sandbox: they are not a survey and not a quote from anyone. Nothing
is created or changed here, so no audit event is written. All arithmetic is in
`app.engine.student_budget`.
"""

from __future__ import annotations

from typing import Any

from app.core import errors
from app.domain.rules import RuleRecord, Rules
from app.engine.money import Money
from app.engine.planner import INDICATIVE
from app.engine.student_budget import (
    HOUSING_KINDS,
    HOUSING_LABELS,
    CityBudget,
    CityCosts,
    budget_for,
    match_cities,
)

COST_PREFIX = "student_costs."
GUIDE_PREFIX = "arrival_guide."
GENERAL = "GENERIC"
STAGES = (
    ("before", "Before you fly"),
    ("first_week", "In your first week"),
    ("first_month", "In your first month"),
)
BUDGET_DISCLAIMER = (
    "Invented figures for the sandbox, not a survey. Compare them with your university's own "
    f"estimate. {INDICATIVE}"
)
_COST_FIELDS = (
    "rent_shared",
    "rent_studio",
    "food",
    "transport",
    "utilities",
    "phone_internet",
    "other",
)


def _city_costs(country: str, record: RuleRecord) -> list[CityCosts]:
    try:
        currency = str(record.value["currency"])
        found = []
        for city, figures in record.value["cities"].items():
            amounts = {f: Money.from_major(int(figures[f]), currency) for f in _COST_FIELDS}
            found.append(CityCosts(country, str(city), currency, **amounts))
        return found
    except (KeyError, TypeError, ValueError) as exc:
        raise errors.ValidationFailed(
            f"The student cost figures for {country} are not in the expected shape."
        ) from exc


def _source(records: list[RuleRecord]) -> dict[str, Any]:
    verified = all(r.verified for r in records)
    checked = sorted(r.last_checked for r in records if r.last_checked)
    return {
        "verified": verified,
        "badge": None if verified else "NOT_VERIFIED",
        "source_url": records[0].source_url,
        "last_checked": checked[-1] if checked else None,
        "note": records[0].note,
    }


def student_budget(
    rules: Rules, *, budget_bdt: Money | None, housing: str, country: str | None
) -> dict[str, Any]:
    """Every city (or those of one country) for one kind of housing, against a monthly budget."""
    if housing not in HOUSING_KINDS:
        raise errors.ValidationFailed(f"Unknown housing: {housing}.")
    records = rules.records_with_prefix(COST_PREFIX)
    names = {code: corridor.name for code, corridor in rules.corridors().items()}
    if country is not None:
        rules.corridor(country)  # an unknown code is a validation failure of its own
        if country not in records:
            raise errors.ValidationFailed(
                f"No student cost figures are loaded for {names.get(country, country)}."
            )
    chosen = {c: r for c, r in records.items() if country in (None, c)}
    budgets: list[CityBudget] = []
    for code, record in chosen.items():
        rate = rules.mid_rate(str(record.value["currency"]))
        budgets += [budget_for(costs, housing, rate) for costs in _city_costs(code, record)]
    rows = match_cities(budgets, budget_bdt)
    items = [{**row.to_api_dict(), "country_name": names[row.budget.costs.country]} for row in rows]
    fitting = None if budget_bdt is None else sum(1 for row in rows if row.fits)
    return {
        "housing": housing,
        "housing_label": HOUSING_LABELS[housing],
        "budget": budget_bdt.to_dict() if budget_bdt else None,
        "countries": [
            {
                "country": code,
                "name": names[code],
                "currency": str(record.value["currency"]),
                "cities": len(record.value["cities"]),
            }
            for code, record in records.items()
        ],
        "items": items,
        "summary": {
            "cities": len(items),
            "fitting": fitting,
            "cheapest": _brief(items[0]) if items else None,
            "dearest": _brief(items[-1]) if items else None,
        },
        "source": _source(list(chosen.values())),
        "synthetic": True,
        "disclaimer": BUDGET_DISCLAIMER,
    }


def _brief(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "country": item["country"],
        "city": item["city"],
        "total": item["total"],
        "total_bdt": item["total_bdt"],
    }


def arrival_guide(rules: Rules, country: str | None) -> dict[str, Any]:
    """What to do before flying and in the first weeks, for one destination (or a general list)."""
    corridor = rules.corridor(country) if country is not None else None
    records = rules.records_with_prefix(GUIDE_PREFIX)
    own = country is not None and country in records
    record = records[country if own and country is not None else GENERAL]
    labels = rules.raw("arrival_labels")
    stages = []
    for key, label in STAGES:
        try:
            items = [
                {"key": item, "label": labels[item]["label"], "hint": labels[item]["hint"]}
                for item in record.value[key]
            ]
        except (KeyError, TypeError) as exc:
            raise errors.ValidationFailed(
                f"The arrival guide for {country} is not in the expected shape."
            ) from exc
        stages.append({"key": key, "label": label, "items": items})
    note = record.note
    if not own:
        where = (
            f"steps specific to {corridor.name} are not loaded" if corridor else "no country given"
        )
        note = f"A general list: {where}. {record.note or INDICATIVE}"
    return {
        "country": country,
        "country_name": corridor.name if corridor else "any country",
        "general": not own,
        "stages": stages,
        "item_count": len({item["key"] for stage in stages for item in stage["items"]}),
        "verified": record.verified,
        "badge": None if record.verified else "NOT_VERIFIED",
        "source_url": record.source_url,
        "last_checked": record.last_checked,
        "note": note,
        "indicative": INDICATIVE,
    }
