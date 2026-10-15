"""Agent tasks: do the work up to the human gate.

"I need to pay GBP 10,000 tuition by 28 October" becomes a real quote, a ranking, a deadline
plan, a KYC and recipient and document check, and a draft PROPOSAL. "How often should I send
GBP 800 a month?" becomes the engine's send plan. The assistant does this with its own
permissions (the RBAC matrix lets it create quotes), every figure comes from the engine, and
the card it returns is built here from engine output, never from model text.

What it never does: create a payment, approve, submit, cancel, allowlist or change a limit.
The human creates the draft and approves with MFA.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from app.ai.intents import Intent
from app.ai.request_parser import ParsedRequest
from app.api.context import AppContext
from app.core import errors
from app.domain.quotes import QuoteRequest
from app.domain.rbac import Actor
from app.domain.rules import load_rules
from app.domain.send_plan import build_send_plan
from app.engine.money import InvalidAmount, Money
from app.engine.planner import plan_deadline

EXAMPLE_PLAN = "Plan GBP 10,000 tuition due 28 October"
EXAMPLE_CADENCE = "How often should I send GBP 800 a month for 9 months?"
DEFAULT_MONTHS = 12

Fact = tuple[str, str, str]  # key, label, value


@dataclass
class TaskResult:
    kind: str
    status: str  # ready | needs_input | error
    card: dict[str, Any]
    facts: list[Fact] = field(default_factory=list)
    quote_id: str | None = None
    recipient_id: str | None = None  # the only saved recipient for the corridor, if exactly one
    missing: list[str] = field(default_factory=list)


def _collected(parsed: ParsedRequest) -> dict[str, Any]:
    """What the assistant already understood, so the next message only has to add the rest."""
    return {
        "amount_minor": parsed.amount_minor if parsed.has_amount else None,
        "currency": parsed.currency if parsed.has_amount else None,
        "due_date": parsed.due_date.isoformat() if parsed.due_date else None,
        "purpose": parsed.purpose,
        "months": parsed.months,
        "charge_code": parsed.charge_code,
    }


def _needs(
    kind: str, what: str, example_key: str, example: str, collected: dict[str, Any] | None = None
) -> TaskResult:
    return TaskResult(
        kind,
        "needs_input",
        {"kind": kind, "status": "needs_input", "missing": [what], "collected": collected or {}},
        [
            ("task.missing", "What I still need to plan this", what),
            (example_key, "Example request", example),
        ],
        missing=[what],
    )


def _failed(kind: str, message: str, example_key: str, example: str) -> TaskResult:
    return TaskResult(
        kind,
        "error",
        {"kind": kind, "status": "error", "message": message},
        [
            ("task.error", "Why the plan could not be built", message),
            (example_key, "Example request", example),
        ],
    )


class TaskRunner:
    def __init__(self, ctx: AppContext) -> None:
        self._ctx = ctx

    def run(self, ai: Actor, intent: Intent, parsed: ParsedRequest) -> TaskResult:
        if intent is Intent.CADENCE:
            return self._send_plan(parsed)
        return self._payment_plan(ai, parsed)

    # --- plan a payment ------------------------------------------------------------------------
    def _payment_plan(self, ai: Actor, parsed: ParsedRequest) -> TaskResult:
        kind = "payment_plan"
        if not parsed.has_amount or parsed.amount_minor is None or parsed.currency is None:
            return _needs(
                kind, "an amount and a currency", "example.plan", EXAMPLE_PLAN, _collected(parsed)
            )
        ctx = self._ctx
        with ctx.db.write() as session:
            rules = load_rules(session)
            corridor = next(
                (c for c in rules.corridors().values() if c.currency == parsed.currency), None
            )
            if corridor is None:
                return _failed(
                    kind, f"I do not serve {parsed.currency} yet", "example.plan", EXAMPLE_PLAN
                )
            saved = [r for r in ctx.recipients.list(session, ai) if r.country == corridor.country]
            only = saved[0] if len(saved) == 1 else None
            request = QuoteRequest(
                target_minor=parsed.amount_minor,
                target_currency=parsed.currency,
                purpose=parsed.purpose,
                destination_country=corridor.country,
                charge_code=parsed.charge_code,
                recipient_id=only.id if only else None,
                due_date=parsed.due_date,
            )
            try:
                quote = ctx.quotes.create(session, ai, rules, request)
            except errors.ApiError as exc:
                return _failed(kind, exc.detail.rstrip("."), "example.plan", EXAMPLE_PLAN)
            kyc = ctx.kyc.view(session, ai, rules)
            checklist = rules.checklist(corridor.country, parsed.purpose)
            provided = {d.kind for d in ctx.documents.list(session, ai)}
            deadline = None
            if parsed.due_date is not None:
                deadline = plan_deadline(
                    due_date=parsed.due_date,
                    now=ctx.clock.now(),
                    calendars=rules.calendars(corridor.country),
                    params=rules.planner_params(),
                ).to_api_dict()
            recipients = [
                {
                    "recipient_id": r.id,
                    "label": ctx.recipients.label(r),
                    "allowlisted": r.allowlisted,
                }
                for r in saved
            ]
            ttl_minutes = rules.quote_ttl_seconds // 60
        return _plan_result(
            parsed, corridor.name, corridor.country, quote, kyc, checklist, provided,
            deadline, recipients, only.id if only else None, ttl_minutes,
        )  # fmt: skip

    # --- plan how often to send ----------------------------------------------------------------
    def _send_plan(self, parsed: ParsedRequest) -> TaskResult:
        kind = "send_plan"
        if not parsed.has_amount or parsed.amount_minor is None or parsed.currency is None:
            return _needs(
                kind, "an amount and a currency", "example.cadence", EXAMPLE_CADENCE,
                _collected(parsed),
            )  # fmt: skip
        months = parsed.months or DEFAULT_MONTHS
        total_minor = parsed.amount_minor * months if parsed.per_month else parsed.amount_minor
        with self._ctx.db.read() as session:
            rules = load_rules(session)
        try:
            plan, body = build_send_plan(
                rules,
                total=Money(total_minor, parsed.currency),
                months=months,
                charge_code=parsed.charge_code,
            )
        except (ValueError, InvalidAmount) as exc:
            return _failed(kind, str(exc).rstrip("."), "example.cadence", EXAMPLE_CADENCE)
        facts: list[Fact] = [
            ("example.cadence", "Example request", EXAMPLE_CADENCE),
            ("cadence.total", "Total to send", plan.total.format()),
            ("cadence.months", "Months the money has to cover", str(months)),
        ]
        by_key = {o.key: o for o in plan.options}
        for raw in body["options"]:
            key, display = raw["key"], raw["display"]
            facts += [
                (f"cadence.{key}.name", "Way of sending", raw["label"]),
                (f"cadence.{key}.transfers", f"{raw['label']}: number of transfers", str(raw["transfers"])),
                (f"cadence.{key}.per_transfer", f"{raw['label']}: amount per transfer", display["per_transfer"]),
                (f"cadence.{key}.provider", f"{raw['label']}: cheapest provider", raw["provider_name"]),
                (f"cadence.{key}.total_cost", f"{raw['label']}: total cost in BDT", display["total_cost"]),
                (f"cadence.{key}.saving", f"{raw['label']}: saving against sending every month", display["saving_vs_monthly"]),
            ]  # fmt: skip
        cheapest = by_key[plan.cheapest_key]
        facts.append(("cadence.cheapest", "Cheapest way on paper", cheapest.label))
        card = {"kind": kind, "status": "ready", "plan": body}
        return TaskResult(kind, "ready", card, facts)


def _plan_result(
    parsed: ParsedRequest,
    country_name: str,
    country: str,
    quote: dict[str, Any],
    kyc: dict[str, Any],
    checklist: dict[str, Any],
    provided: set[str],
    deadline: dict[str, Any] | None,
    recipients: list[dict[str, Any]],
    only_recipient: str | None,
    ttl_minutes: int,
) -> TaskResult:
    results = sorted(quote["results"], key=lambda r: r["rank"])
    best, others = results[0], results[1:]
    keys = [item["key"] for item in checklist["items"]]
    ready = sum(1 for key in keys if key in provided)
    allowlisted = sum(1 for r in recipients if r["allowlisted"])

    def shown(r: dict[str, Any]) -> dict[str, Any]:
        d = r["display"]
        return {
            "provider_id": r["provider_id"],
            "provider_name": r["provider_name"],
            "cost_pct": d["cost_pct"],
            "parent_pays": d["parent_pays"],
            "total_cost": d["total_cost"],
            "shortfall": d["shortfall"],
            "has_shortfall": r["shortfall_foreign_minor"] > 0,
            "charge_code": r["charge_code"],
            "eta_business_days": r["eta_business_days"],
        }

    missing = ["reference"] + ([] if only_recipient else ["recipient_id"])
    plan_link = f"/compare?quote={quote['quote_id']}&provider={best['provider_id']}"
    if recipients:
        recipient_step = (
            (
                "done",
                f"{allowlisted} allowlisted recipient{'s' if allowlisted != 1 else ''}",
                "/recipients",
            )
            if allowlisted
            else ("todo", "Allowlist your recipient with a fresh MFA code", "/recipients")
        )
    else:
        recipient_step = ("todo", "Add the university as a recipient", "/recipients")
    steps = [
        _step("quote", "Quote made from your request", "done", f"Valid for {ttl_minutes} minutes", None),
        _step(
            "deadline", "Deadline planned" if deadline else "Add a due date to plan the deadline",
            "done" if deadline else "todo",
            f"Send by {deadline['latest_send_date']}" if deadline else "Tell me the university's due date",
            None,
        ),
        _step("kyc", "Identity check (simulated)", "done" if kyc["status"] == "VERIFIED" else "todo", kyc["message"], "/"),
        _step("recipient", "Recipient ready", recipient_step[0], recipient_step[1], recipient_step[2]),
        _step(
            "documents", "Documents ready", "done" if ready >= len(keys) else "todo",
            f"{ready} of {len(keys)} documents ready", "/documents",
        ),
        _step("draft", "Create the draft", "todo", "You confirm the recipient and the payment reference", plan_link),
        _step("approve", "Approve", "todo", "Only you can, with a fresh MFA code", None),
    ]  # fmt: skip
    card = {
        "kind": "payment_plan",
        "status": "ready",
        "request": {
            "amount": quote["target"],
            "purpose": parsed.purpose,
            "country": country,
            "country_name": country_name,
            "due_date": parsed.due_date.isoformat() if parsed.due_date else None,
            "charge_code": parsed.charge_code,
        },
        "quote": {"quote_id": quote["quote_id"], "expires_at": quote["expires_at"]},
        "best": shown(best),
        "alternatives": [shown(r) for r in others],
        "deadline": deadline,
        "recipients": recipients,
        "steps": steps,
        "draft": {
            "quote_id": quote["quote_id"],
            "provider_id": best["provider_id"],
            "recipient_id": only_recipient,
            "missing": missing,
        },
    }
    facts: list[Fact] = [
        ("example.plan", "Example request", EXAMPLE_PLAN),
        ("request.country", "Destination country", country_name),
        ("request.charge_code", "Charge code requested", parsed.charge_code),
        ("plan.best", "Lowest-cost provider", best["provider_name"]),
        ("recipient.matching", "Recipients saved for this country", str(len(recipients))),
        ("recipient.allowlisted", "Of those, allowlisted for payments", str(allowlisted)),
        ("docs.provided", "Checklist documents already added", str(ready)),
        ("docs.total", "Documents on the checklist", str(len(keys))),
    ]
    return TaskResult(
        "payment_plan", "ready", card, facts, quote["quote_id"], only_recipient, missing
    )


def _step(key: str, label: str, state: str, detail: str, link: str | None) -> dict[str, Any]:
    return {"key": key, "label": label, "state": state, "detail": detail, "link": link}
