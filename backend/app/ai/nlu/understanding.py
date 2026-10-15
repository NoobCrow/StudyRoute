"""Understand a message: the trained reader proposes, the deterministic code verifies.

Two readers look at every message. The rule-based reader (``request_parser`` and ``intents``) is
the safe baseline. The trained reader (``runtime.Reader``) copes with wording the rules do not
know. They are combined like this:

* **Values** come from the typed result of ``normalize``, never from model text. If the rules and
  the model read the same field differently, the field is left empty and the assistant asks.
* **Intent**: the model's choice is used only when it is confident enough, and an intent that
  starts something (a quote, a draft, an approval request) needs more confidence than one that
  only explains. Otherwise the rules decide.
* **ATTACK**: a confident "this is an instruction override or an action request" blocks the
  message exactly like the existing policy filter does. It can only add a block, never remove one.

Nothing here can approve, submit or change anything. It only decides what to ask the engine.
"""

from __future__ import annotations

from collections.abc import Collection
from dataclasses import dataclass, replace
from datetime import date
from typing import Any

from app.ai.intents import _NOT_A_PLAN, Intent, choose_intent, classify
from app.ai.nlu import normalize
from app.ai.nlu.runtime import Prediction, Reader
from app.ai.nlu.schema import ACTION_INTENTS
from app.ai.nlu.slots import SlotValues, Span, read_slots
from app.ai.request_parser import ParsedRequest, parse_request


@dataclass(frozen=True)
class Pending:
    """A task the assistant started and is waiting to finish (it asked for something)."""

    kind: str  # "payment_plan" or "send_plan"
    amount_minor: int | None = None
    currency: str | None = None
    due_date: date | None = None
    purpose: str | None = None
    months: int | None = None
    charge_code: str | None = None


@dataclass(frozen=True)
class Understanding:
    intent: Intent
    parsed: ParsedRequest
    source: str  # "trained" or "rules"
    model_id: str | None = None
    model_sha256: str | None = None
    model_intent: str | None = None
    confidence: float | None = None
    attack: bool = False
    out_of_scope: bool = False
    spans: tuple[Span, ...] = ()
    problems: tuple[str, ...] = ()
    conflicts: tuple[str, ...] = ()
    continued: bool = False
    hint: str | None = None  # shown to the person when a value had to be left empty

    def to_api(self) -> dict[str, Any]:
        parsed = self.parsed
        return {
            "source": self.source,
            "model": self.model_id,
            "model_sha256": self.model_sha256[:12] if self.model_sha256 else None,
            "intent": self.intent.value,
            "model_intent": self.model_intent,
            "confidence": round(self.confidence, 3) if self.confidence is not None else None,
            "attack": self.attack,
            "out_of_scope": self.out_of_scope,
            "continued_earlier_task": self.continued,
            "spans": [
                {"label": s.label, "text": s.text, "start": s.start, "end": s.end}
                for s in self.spans
            ],
            "values": {
                "amount_minor": parsed.amount_minor,
                "currency": parsed.currency,
                "due_date": parsed.due_date.isoformat() if parsed.due_date else None,
                "months": parsed.months,
                "charge_code": parsed.charge_code,
                "purpose": parsed.purpose,
            },
            "conflicts": list(self.conflicts),
            "unreadable": list(self.problems),
        }


def _agree(rules: object | None, model: object | None, name: str, conflicts: list[str]) -> Any:
    """One field from two readers: the same, or whichever one found it; a clash leaves it empty."""
    if rules is not None and model is not None and rules != model:
        conflicts.append(name)
        return None
    return rules if rules is not None else model


def _fuse(base: ParsedRequest, slots: SlotValues, text: str) -> tuple[ParsedRequest, list[str]]:
    conflicts: list[str] = []
    amount = (base.amount_minor, base.currency) if base.has_amount else None
    found = (
        (slots.amount_minor, slots.currency)
        if slots.amount_minor is not None and slots.currency is not None
        else None
    )
    pair = _agree(amount, found, "amount", conflicts)
    due = _agree(base.due_date, slots.due_date, "due_date", conflicts)
    months = _agree(base.months, slots.months, "months", conflicts)
    explicit_purpose = normalize.parse_purpose(text)
    purpose = slots.purpose or base.purpose
    if explicit_purpose and slots.purpose and explicit_purpose != slots.purpose:
        purpose = explicit_purpose  # the words in the message win over a model label
    charge = slots.charge or base.charge_code
    return (
        replace(
            base,
            amount_minor=pair[0] if pair else None,
            currency=pair[1] if pair else None,
            due_date=due,
            months=months,
            purpose=purpose,
            charge_code=charge,
        ),
        conflicts,
    )


def _describe(rules: ParsedRequest, slots: SlotValues) -> str:
    def money(minor: int | None, currency: str | None) -> str:
        return f"{currency} {minor / 100:,.2f}" if minor is not None and currency else "no amount"

    return (
        f"I read the amount two ways ({money(rules.amount_minor, rules.currency)} and "
        f"{money(slots.amount_minor, slots.currency)}); please type it once, for example GBP 10,000"
    )


def _model_intent(
    prediction: Prediction, rules_intent: Intent, text: str, limits: dict[str, float]
) -> tuple[Intent, bool, bool]:
    """(intent, attack, out_of_scope) after the thresholds and the safety refinements."""
    name, confidence = prediction.intent, prediction.confidence
    if name == "ATTACK":
        if confidence >= limits["attack"]:
            return Intent.HELP, True, False
        return rules_intent, False, False
    if confidence < limits["intent"]:
        return rules_intent, False, False
    if name == "OUT_OF_SCOPE":
        return Intent.HELP, False, True
    candidate = Intent(name)
    if name in ACTION_INTENTS and confidence < limits["action"]:
        return rules_intent, False, False  # starting something needs more evidence than explaining
    if candidate in (Intent.PLAN, Intent.CADENCE) and _NOT_A_PLAN.search(text):
        candidate = classify(text)  # a question about limits or legality never starts a quote
    return candidate, False, False


def _continue(
    pending: Pending, parsed: ParsedRequest, intent: Intent, text: str
) -> tuple[Intent, ParsedRequest] | None:
    """Finish the task the assistant asked about, if this message supplies what was missing."""
    supplies = (
        parsed.has_amount
        or parsed.due_date is not None
        or parsed.months is not None
        or normalize.parse_charge(text) is not None
        or normalize.parse_purpose(text) is not None
    )
    if not supplies or intent not in (Intent.HELP, Intent.PLAN, Intent.CADENCE):
        return None
    cadence = pending.kind == "send_plan"
    merged = replace(
        parsed,
        amount_minor=parsed.amount_minor if parsed.has_amount else pending.amount_minor,
        currency=parsed.currency if parsed.has_amount else pending.currency,
        due_date=parsed.due_date or pending.due_date,
        months=parsed.months or pending.months,
        purpose=(
            parsed.purpose if normalize.parse_purpose(text) else (pending.purpose or parsed.purpose)
        ),
        charge_code=(
            parsed.charge_code
            if normalize.parse_charge(text)
            else (pending.charge_code or parsed.charge_code)
        ),
        per_month=parsed.per_month or cadence,
    )
    return (Intent.CADENCE if cadence else Intent.PLAN), merged


def understand(
    text: str,
    today: date,
    currencies: Collection[str],
    *,
    has_context: bool,
    reader: Reader | None = None,
    pending: Pending | None = None,
    prediction: Prediction | None = None,  # a prediction already made (used when tuning)
    limits: dict[str, float] | None = None,  # thresholds to use instead of the manifest's
) -> Understanding:
    base = parse_request(text, currencies, today)
    if reader is None:
        intent = choose_intent(text, base, has_context=has_context)
        parsed, continued = base, False
        if pending is not None and (done := _continue(pending, base, intent, text)):
            intent, parsed = done
            continued = True
        return Understanding(intent, parsed, "rules", continued=continued)

    prediction = prediction or reader.predict(text)
    slots = read_slots(prediction.spans, today, currencies)
    parsed, conflicts = _fuse(base, slots, text)
    hint = _describe(base, slots) if "amount" in conflicts else None
    rules_intent = choose_intent(text, parsed, has_context=has_context)
    limits = limits or {k: float(v) for k, v in reader.manifest["thresholds"].items()}
    intent, attack, out_of_scope = _model_intent(prediction, rules_intent, text, limits)
    continued = False
    if pending is not None and not attack and (done := _continue(pending, parsed, intent, text)):
        intent, parsed = done
        continued = True
    return Understanding(
        intent=intent,
        parsed=parsed,
        source="trained",
        model_id=reader.model_id,
        model_sha256=reader.sha256,
        model_intent=prediction.intent,
        confidence=prediction.confidence,
        attack=attack,
        out_of_scope=out_of_scope,
        spans=tuple(prediction.spans),
        problems=tuple(slots.problems),
        conflicts=tuple(conflicts),
        continued=continued,
        hint=hint,
    )
