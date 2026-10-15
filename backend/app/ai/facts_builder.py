"""Turn engine output into FACTS. All figures are formatted here, never by the model."""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal
from typing import Any

from app.ai.facts import FactSet
from app.domain.rules import Rules
from app.engine.money import Money

_PCT = Decimal("0.01")


def _bdt(minor: int) -> str:
    return Money(minor, "BDT").format()


def _pp(value: Decimal) -> str:
    return f"{value.quantize(_PCT, rounding=ROUND_HALF_UP)} percentage points"


def build_rule_facts(facts: FactSet, rules: Rules) -> None:
    per_tx = Money.from_major(rules.per_transaction_limit_usd, "USD").format()
    daily = Money.from_major(rules.daily_limit_usd, "USD").format()
    facts.add(
        "limit.per_transaction",
        "Sandbox per-transaction cap (our own choice, not a legal limit)",
        per_tx,
    )
    facts.add("limit.daily", "Sandbox daily cap (our own choice, not a legal limit)", daily)
    living = rules.record("bangladesh_rules.living_expense_usd_per_month")
    uplift = rules.record("bangladesh_rules.living_expense_high_cost_uplift_pct")
    status = "verified" if living.verified else "NOT verified, secondary source only"
    facts.add(
        "bd.living_expense",
        f"Indicative Bangladesh living-expense figure per month ({status})",
        Money.from_major(living.value, "USD").format(),
    )
    facts.add("bd.living_uplift", f"Indicative high-cost uplift ({status})", f"{uplift.value}%")
    facts.add(
        "plan.settlement_days",
        "Assumed settlement time in business days",
        str(rules.planner_params().settlement_business_days),
    )
    facts.add(
        "plan.buffer_days",
        "Safety buffer in business days",
        str(rules.planner_params().buffer_days),
    )
    cutoff = rules.planner_params().cutoff.strftime("%H:%M")
    facts.add("plan.cutoff", "Assumed bank cut-off in Dhaka time (not verified)", cutoff)
    facts.add("quote.ttl", "How long a quote stays valid, in seconds", str(rules.quote_ttl_seconds))
    facts.add(
        "mfa.ttl", "How long an MFA proof stays valid, in seconds", str(rules.mfa_proof_ttl_seconds)
    )


def build_quote_facts(facts: FactSet, quote: dict[str, Any]) -> None:
    facts.add("quote.target", "Amount the university should receive", quote["target"]["formatted"])
    facts.add("quote.status", "Quote status", quote["status"])
    facts.add("quote.mid_rate", "Synthetic mid-market rate", quote["mid_rate"]["display"])
    facts.add("quote.expires_at", "Quote expiry time (UTC)", quote["expires_at"])
    results = quote["results"]
    for r in results:
        pid, name, d = r["provider_id"], r["provider_name"], r["display"]
        facts.add(f"{pid}.name", "Provider name", name)
        facts.add(f"{pid}.rank", f"{name}: rank by true total cost", str(r["rank"]))
        facts.add(
            f"{pid}.cost_pct",
            f"{name}: true total cost as a percentage of the amount",
            d["cost_pct"],
        )
        facts.add(f"{pid}.margin_pct", f"{name}: hidden FX margin over mid-market", d["margin_pct"])
        facts.add(f"{pid}.rate", f"{name}: selling rate in BDT per unit", r["provider_rate"])
        facts.add(f"{pid}.fx_cost", f"{name}: cost of the FX margin", d["fx_cost"])
        facts.add(f"{pid}.fixed_fee", f"{name}: fixed fee", d["fixed_fee"])
        facts.add(f"{pid}.swift_fee", f"{name}: SWIFT fee", d["swift_fee"])
        facts.add(
            f"{pid}.intermediary_fee", f"{name}: intermediary bank fee", d["intermediary_fee"]
        )
        facts.add(f"{pid}.receiving_fee", f"{name}: receiving bank fee", d["receiving_fee"])
        facts.add(f"{pid}.total_cost", f"{name}: total cost in BDT", d["total_cost"])
        facts.add(f"{pid}.parent_pays", f"{name}: the parent pays in BDT", d["parent_pays"])
        facts.add(
            f"{pid}.shortfall", f"{name}: amount the university may receive short", d["shortfall"]
        )
        facts.add(
            f"{pid}.receives", f"{name}: amount the university receives", d["beneficiary_receives"]
        )
        facts.add(f"{pid}.charge_code", f"{name}: charge code applied", r["charge_code"])
        facts.add(
            f"{pid}.eta", f"{name}: estimated business days to settle", str(r["eta_business_days"])
        )
    if quote.get("deadline_fit"):
        _add_deadline_facts(
            facts, quote["deadline_fit"], {r["provider_id"]: r["provider_name"] for r in results}
        )
    ordered = sorted(results, key=lambda r: r["rank"])
    for index, cheaper in enumerate(ordered):
        for dearer in ordered[index + 1 :]:
            _add_difference(facts, cheaper, dearer)


def build_stress_facts(facts: FactSet, stress: dict[str, Any]) -> None:
    """The currency-drop what-if, as the engine priced it."""
    facts.add("stress.provider", "Provider the stress test used", stress["provider_name"])
    facts.add("stress.currency", "Currency being paid", stress["target"]["currency"])
    facts.add(
        "stress.baseline_pays",
        "Today: the parent pays in BDT",
        stress["baseline"]["display"]["parent_pays"],
    )
    facts.add("stress.count", "Number of stress scenarios", str(len(stress["scenarios"])))
    facts.add("stress.assumption", "What the stress test assumes", stress["assumption"])
    for index, row in enumerate(stress["scenarios"]):
        label = f"If the foreign currency costs {row['drop_pct']} more"
        facts.add(f"stress.{index}.drop", f"{label}: the size of the drop", row["drop_pct"])
        facts.add(
            f"stress.{index}.pays",
            f"{label}: the parent pays in BDT",
            row["display"]["parent_pays"],
        )
        facts.add(f"stress.{index}.extra", f"{label}: extra BDT to pay", row["display"]["extra"])
        facts.add(
            f"stress.{index}.extra_pct", f"{label}: extra as a share", row["display"]["extra_pct"]
        )


def _add_deadline_facts(facts: FactSet, fit: dict[str, Any], names: dict[str, str]) -> None:
    """Who arrives before the due date. The engine decided; these are its answers as facts."""
    facts.add("deadline.due_date", "University due date", fit["due_date"])
    facts.add("deadline.send_date", "Date the money would be sent", fit["send_date"])
    for entry in fit["providers"]:
        pid, name = entry["provider_id"], names[entry["provider_id"]]
        facts.add(f"{pid}.arrives_on", f"{name}: date the money would arrive", entry["arrives_on"])
        facts.add(
            f"{pid}.in_time",
            f"{name}: arrives by the due date",
            "yes" if entry["meets_deadline"] else "no",
        )
    for key, label, pid in (
        ("cheapest", "Lowest-cost provider overall", fit["cheapest_overall"]),
        ("best", "Lowest-cost provider that arrives in time", fit["best_in_time"]),
        ("fastest", "Fastest provider", fit["fastest"]),
    ):
        if pid is not None:
            facts.add(f"deadline.{key}", label, names[pid])
            facts.add(f"deadline.{key}_id", f"{label} (provider id)", pid)
    facts.add(
        "deadline.cheapest_misses",
        "The lowest-cost provider would arrive after the due date",
        "yes" if fit["cheapest_misses_deadline"] else "no",
    )


def _add_difference(facts: FactSet, cheaper: dict[str, Any], dearer: dict[str, Any]) -> None:
    a, b = cheaper["provider_id"], dearer["provider_id"]
    names = f"{cheaper['provider_name']} vs {dearer['provider_name']}"
    cost = Decimal(dearer["cost_pct"]) - Decimal(cheaper["cost_pct"])
    margin = Decimal(dearer["margin_pct"]) - Decimal(cheaper["margin_pct"])
    saved = dearer["total_cost_bdt_minor"] - cheaper["total_cost_bdt_minor"]
    facts.add(f"diff.{a}.{b}.cost_pct", f"{names}: difference in total cost percentage", _pp(cost))
    facts.add(f"diff.{a}.{b}.margin_pct", f"{names}: difference in FX margin", _pp(margin))
    facts.add(f"diff.{a}.{b}.total_cost", f"{names}: difference in total cost", _bdt(saved))


def build_payment_facts(facts: FactSet, payment: dict[str, Any]) -> None:
    facts.add("payment.state", "Payment state", payment["state"])
    facts.add("payment.provider", "Chosen provider", payment["provider_name"])
    facts.add("payment.target", "Amount to deliver", payment["target"]["formatted"])
    facts.add("payment.parent_pays", "The parent pays in BDT", payment["parent_pays"])
    if payment.get("due_date"):
        facts.add("payment.due_date", "University due date", payment["due_date"])
    if payment.get("latest_send_date"):
        facts.add("payment.latest_send_date", "Latest send date", payment["latest_send_date"])
    if payment.get("uetr"):
        facts.add("payment.uetr", "UETR (tracking reference)", payment["uetr"])
    for blocker in payment.get("readiness", {}).get("blockers", []):
        facts.add(f"blocker.{blocker['code']}", "Something blocking approval", blocker["message"])


def build_plan_facts(facts: FactSet, plan: dict[str, Any], country_name: str) -> None:
    facts.add("plan.country", "Destination country", country_name)
    facts.add("plan.due_date", "University due date", plan["due_date"])
    facts.add("plan.latest", "Latest send date", plan["latest_send_date"])
    facts.add("plan.recommended", "Recommended send date", plan["recommended_send_date"])
    facts.add(
        "plan.earliest", "Earliest date a payment sent now would count", plan["earliest_send_date"]
    )
    facts.add("plan.status", "Deadline status", plan["status"])
    for warning in plan["warnings"]:
        facts.add(f"plan.warning.{warning['code']}", "Planner warning", warning["message"])


def build_kyc_facts(facts: FactSet, kyc: dict[str, Any]) -> None:
    facts.add("kyc.status", "Mock KYC status (simulated)", kyc["status"])
    facts.add("kyc.message", "What the KYC status means", kyc["message"])


def build_checklist_facts(facts: FactSet, checklist: dict[str, Any]) -> None:
    facts.add(
        "checklist.title", "Checklist", f"{checklist['country']} {checklist['purpose'].lower()}"
    )
    for item in checklist["items"]:
        facts.add(f"checklist.{item['key']}", "Document the bank may ask for", item["label"])
