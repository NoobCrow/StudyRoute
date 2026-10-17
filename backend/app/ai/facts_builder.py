"""Turn engine output into FACTS. All figures are formatted here, never by the model."""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal
from typing import Any

from app.ai.facts import FactSet
from app.ai.student_topic import StudentTopic
from app.domain.rules import Rules
from app.domain.student_guide import student_budget
from app.engine.money import Money
from app.engine.student_budget import HOUSING_LABELS

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
    status = (
        "verified"
        if living.verified
        else "NOT verified, secondary source only, not in the official circular"
    )
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


LIST_MAX = 5


def _add_cost_row(facts: FactSet, prefix: str, row: dict[str, Any], *, judged: bool) -> None:
    facts.add(f"{prefix}.city", "City", row["city"])
    facts.add(f"{prefix}.country_name", "Country", row["country_name"])
    facts.add(
        f"{prefix}.total", f"A month in {row['city']}, local money", row["total"]["formatted"]
    )
    facts.add(
        f"{prefix}.total_bdt", f"A month in {row['city']}, in taka", row["total_bdt"]["formatted"]
    )
    if judged:
        facts.add(
            f"{prefix}.fits", f"{row['city']} fits the budget", "yes" if row["fits"] else "no"
        )
        if row["fits"]:
            facts.add(
                f"{prefix}.spare", f"{row['city']}: taka to spare", row["spare_bdt"]["formatted"]
            )
        else:
            facts.add(f"{prefix}.gap", f"{row['city']}: taka short", row["gap_bdt"]["formatted"])


def _add_city_detail(
    facts: FactSet, rules: Rules, topic: StudentTopic, row: dict[str, Any]
) -> None:
    facts.add("cost.city", "City asked about", row["city"])
    facts.add("cost.country_name", "Country of the city", row["country_name"])
    facts.add("cost.currency", "Currency of the city", row["currency"])
    for line in row["lines"]:
        facts.add(f"cost.line.{line['key']}", f"{line['label']} in a month", line["formatted"])
    facts.add("cost.total", "A month in this city, local money", row["total"]["formatted"])
    facts.add("cost.total_bdt", "A month in this city, in taka", row["total_bdt"]["formatted"])
    facts.add("cost.rent_bdt", "The rent in taka", row["rent_bdt"]["formatted"])
    facts.add("cost.rent_share", "Rent as a share of the month", f"{row['rent_share_pct']}%")
    facts.add("cost.rate", "Synthetic rate used (BDT per unit)", row["rate_bdt_per_unit"])
    other = "studio" if topic.housing == "shared" else "shared"
    rows = student_budget(
        rules, budget_bdt=topic.budget_bdt, housing=other, country=row["country"]
    )["items"]
    twin = next(r for r in rows if r["city"] == row["city"])
    facts.add("cost.other_housing", "The other kind of housing", HOUSING_LABELS[other])
    facts.add(
        "cost.other_total", "A month with the other kind of housing", twin["total"]["formatted"]
    )
    facts.add("cost.other_total_bdt", "That month in taka", twin["total_bdt"]["formatted"])
    if topic.budget_bdt is not None:
        facts.add("cost.fits", "This city fits the budget", "yes" if row["fits"] else "no")
        if row["fits"]:
            facts.add("cost.spare", "Taka to spare each month", row["spare_bdt"]["formatted"])
        else:
            facts.add("cost.gap", "Taka short each month", row["gap_bdt"]["formatted"])


def build_student_cost_facts(facts: FactSet, rules: Rules, topic: StudentTopic) -> None:
    """A month in a city, a country's cities, or which cities fit a budget: the engine's figures."""
    overview = student_budget(
        rules, budget_bdt=topic.budget_bdt, housing=topic.housing, country=None
    )
    facts.add("cost.verified", "Are the cost figures verified", "no, invented for the sandbox")
    facts.add("cost.disclaimer", "How to read the cost figures", overview["disclaimer"])
    facts.add("cost.housing", "Kind of housing", overview["housing_label"])
    facts.add(
        "cost.countries",
        "Countries with student cost figures",
        ", ".join(c["name"] for c in overview["countries"]),
    )
    judged = topic.budget_bdt is not None
    if judged:
        facts.add("cost.budget", "Monthly budget in taka", overview["budget"]["formatted"])
    if topic.country is not None and topic.country not in {
        c["country"] for c in overview["countries"]
    }:
        facts.add(
            "cost.no_figures", "A country with no cost figures", rules.corridor(topic.country).name
        )
        return
    scoped = overview
    if topic.country is not None:
        scoped = student_budget(
            rules, budget_bdt=topic.budget_bdt, housing=topic.housing, country=topic.country
        )
        facts.add("cost.country_name", "Country asked about", rules.corridor(topic.country).name)
    items = scoped["items"]
    facts.add("cost.count", "Number of cities", str(len(items)))
    if judged:
        facts.add("cost.fitting", "Cities that fit the budget", str(scoped["summary"]["fitting"]))
    if topic.city is not None:
        row = next(r for r in items if r["city"] == topic.city)
        _add_city_detail(facts, rules, topic, row)
        return
    fitting = [r for r in items if r["fits"]]  # the cities that fit, or the cheapest if none
    shown = (fitting[:LIST_MAX] or items[:1]) if judged else items[:LIST_MAX]
    facts.add("cost.listed", "Number of cities listed", str(len(shown)))
    for index, row in enumerate(shown):
        _add_cost_row(facts, f"cost.c{index}", row, judged=judged)


def build_arrival_facts(facts: FactSet, guide: dict[str, Any]) -> None:
    """What to do before flying and in the first weeks: the guide's own steps, in order."""
    facts.add("arrival.country", "Destination of the guide", guide["country_name"])
    facts.add("arrival.general", "Is this the general list", "yes" if guide["general"] else "no")
    facts.add("arrival.count", "Number of steps in the guide", str(guide["item_count"]))
    facts.add("arrival.note", "How far to trust the guide", guide["note"])
    for stage in guide["stages"]:
        facts.add(
            f"arrival.{stage['key']}",
            f"Steps: {stage['label'].lower()}",
            "; ".join(item["label"] for item in stage["items"]),
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


def build_review_facts(facts: FactSet, review: dict[str, Any]) -> None:
    """The sandbox bank's review of this payment, in the words the parent's page already uses."""
    facts.add("review.headline", "Bank check", review["headline"])
    facts.add("review.plain", "What the bank check means", review["plain"])
    clock = review["clock"]
    if clock["running"]:
        left = clock["minutes_left"]
        hours = abs(left) // 60
        text = (
            f"about {hours} hours left of the bank's {clock['target_hours']}-hour target"
            if left >= 0
            else f"about {hours} hours past the bank's {clock['target_hours']}-hour target"
        )
        facts.add("review.clock", "How long the bank has had it", text)
    ai = review.get("ai")
    if ai:
        facts.add(
            "review.score",
            "AI risk score",
            f"{ai['score']} out of 100, {ai['band'].lower()} risk",
        )
        facts.add(
            "review.warning",
            "Warning",
            "A warning is shown: take care before authorizing." if ai["warning"] else "No warning.",
        )
        for factor in ai["factors"]:
            facts.add(
                f"review.factor.{factor['code']}",
                factor["title"],
                f"{factor['title']}: {factor['plain']}",
            )
    for index, signal in enumerate(review["signals"]):
        facts.add(
            f"review.signal.{index}",
            "A reason for the bank check",
            f"{signal['title']}: {signal['means']}",
        )
        facts.add(
            f"review.prepare.{index}",
            f"To prepare: {signal['title']}",
            "; ".join(signal["prepare"]),
        )
    if review.get("reviewer_asked"):
        facts.add("review.asked", "What the bank asked", review["reviewer_asked"])
    if review.get("decision_reason"):
        facts.add("review.reason", "Why the bank said no", review["decision_reason"])


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
