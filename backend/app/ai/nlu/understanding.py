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

import re
from collections.abc import Collection
from dataclasses import dataclass, field, replace
from datetime import date
from typing import Any

from app.ai.dialogue.state import SlotState
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
    # What the dialogue has done so far (see ``app.ai.dialogue``). The page sends these back.
    date_skipped: bool = False  # the person said there is no deadline
    awaiting_confirmation: bool = False  # the last assistant turn was a read-back
    turns: int = 0  # assistant turns so far in this task
    asked: tuple[bool, bool, bool] = (False, False, False)  # amount, date, months were asked
    conf_amount: float | None = None  # how sure the reader was about each value when it was read
    conf_date: float | None = None
    conf_months: float | None = None
    extra_amount: bool = False  # an earlier message mentioned more than one amount


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
    evidence: dict[str, SlotState] = field(default_factory=dict)  # amount, date, months
    confirmed: bool = False  # the person confirmed the read-back
    date_skipped: bool = False
    rejected: bool = False  # the person said the read-back was wrong
    amount_candidates: int = 0  # how many amounts the model marked in the message

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
            "amount_candidates": self.amount_candidates,
            "evidence": {
                name: {
                    "present": s.present,
                    "conflict": s.conflict,
                    "source": s.source,
                    "confidence": round(s.confidence, 3),
                }
                for name, s in self.evidence.items()
            },
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
    if rules_intent in (Intent.STRESS, Intent.COSTS, Intent.ARRIVAL):
        return rules_intent, False, False  # the model never saw these questions; the rule is exact
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


_YES = re.compile(
    r"^\W*(yes|yeah|yep|yup|ok|okay|sure|correct|right|confirmed?|proceed|go ahead|please do|do it"
    r"|that is (right|correct)|that's (right|correct))\b",
    re.I,
)
_NO = re.compile(
    r"^\W*(no|nope|nah|wrong|incorrect|not (right|correct)|that is (wrong|not right)"
    r"|that's (wrong|not right))\b",
    re.I,
)
_SKIP = re.compile(
    r"\b(no (deadline|date|due)|don't know|dont know|do not know|not sure|no idea|skip( it| this)?"
    r"|none|whenever)\b",
    re.I,
)


@dataclass(frozen=True)
class Continuation:
    """What an answer to the assistant's last question means for the task it started."""

    intent: Intent
    parsed: ParsedRequest
    confirmed: bool = False
    date_skipped: bool = False
    rejected: bool = False


def _merged(pending: Pending, parsed: ParsedRequest, text: str) -> ParsedRequest:
    cadence = pending.kind == "send_plan"
    return replace(
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


def _continue(
    pending: Pending, parsed: ParsedRequest, intent: Intent, text: str
) -> Continuation | None:
    """Finish the task the assistant asked about, if this message answers its question."""
    supplies = (
        parsed.has_amount
        or parsed.due_date is not None
        or parsed.months is not None
        or normalize.parse_charge(text) is not None
        or normalize.parse_purpose(text) is not None
    )
    task = Intent.CADENCE if pending.kind == "send_plan" else Intent.PLAN
    if not supplies:  # a short answer: yes, no, or "no deadline"
        if pending.awaiting_confirmation and _YES.match(text):
            return Continuation(task, _merged(pending, parsed, text), confirmed=True,
                                date_skipped=pending.date_skipped)  # fmt: skip
        if pending.awaiting_confirmation and _NO.match(text):
            return Continuation(task, _merged(pending, parsed, text), rejected=True)
        if _SKIP.search(text) and pending.turns > 0:
            return Continuation(task, _merged(pending, parsed, text), date_skipped=True)
        return None
    if intent not in (Intent.HELP, Intent.PLAN, Intent.CADENCE):
        return None
    return Continuation(task, _merged(pending, parsed, text), date_skipped=pending.date_skipped)


def _evidence(
    base: ParsedRequest,
    slots: SlotValues,
    prediction: Prediction,
    conflicts: list[str],
    parsed: ParsedRequest,
) -> dict[str, SlotState]:
    """How each value was read: by whom, and how sure the model was of the words it marked."""

    def sure(*labels: str) -> float:
        found = [
            c for s, c in zip(prediction.spans, prediction.span_confidence, strict=True)
            if s.label in labels
        ]  # fmt: skip
        return min(found) if found else 0.0

    def one(name: str, rules: bool, model: bool, present: bool, *labels: str) -> SlotState:
        if name in conflicts:
            return SlotState(conflict=True)
        if not present:
            return SlotState()
        source = "both" if rules and model else ("model" if model else "rules")
        return SlotState(True, False, source, sure(*labels) if model else 0.0)

    return {
        "amount": one(
            "amount", base.has_amount,
            slots.amount_minor is not None and slots.currency is not None,
            parsed.has_amount, "AMOUNT", "CURRENCY",
        ),
        "date": one("due_date", base.due_date is not None, slots.due_date is not None,
                    parsed.due_date is not None, "DATE"),
        "months": one("months", base.months is not None, slots.months is not None,
                      parsed.months is not None, "DURATION"),
    }  # fmt: skip


def _earlier(
    now: dict[str, SlotState], pending: Pending, parsed: ParsedRequest, *, confirmed: bool
) -> dict[str, SlotState]:
    """Values held from earlier turns count as read before, or as certain once confirmed."""
    held = {
        "amount": (parsed.has_amount, pending.amount_minor is not None, pending.conf_amount),
        "date": (parsed.due_date is not None, pending.due_date is not None, pending.conf_date),
        "months": (parsed.months is not None, pending.months is not None, pending.conf_months),
    }
    out = dict(now)
    for name, (present, was_held, conf) in held.items():
        if present and not out[name].present and not out[name].conflict and was_held:
            certain = confirmed or conf is None
            out[name] = SlotState(True, False, "earlier", 1.0 if certain else conf or 0.0)
    return out


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
            intent, parsed, continued = done.intent, done.parsed, True
        return Understanding(intent, parsed, "rules", continued=continued)

    prediction = prediction or reader.predict(text)
    slots = read_slots(prediction.spans, today, currencies)
    parsed, conflicts = _fuse(base, slots, text)
    evidence = _evidence(base, slots, prediction, conflicts, parsed)
    hint = _describe(base, slots) if "amount" in conflicts else None
    rules_intent = choose_intent(text, parsed, has_context=has_context)
    limits = limits or {k: float(v) for k, v in reader.manifest["thresholds"].items()}
    intent, attack, out_of_scope = _model_intent(prediction, rules_intent, text, limits)
    continued = confirmed = skipped = rejected = False
    if pending is not None and not attack and (done := _continue(pending, parsed, intent, text)):
        intent, parsed, continued = done.intent, done.parsed, True
        confirmed, skipped, rejected = done.confirmed, done.date_skipped, done.rejected
        evidence = _earlier(evidence, pending, parsed, confirmed=confirmed)
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
        evidence=evidence,
        amount_candidates=sum(1 for s in prediction.spans if s.label == "AMOUNT"),
        confirmed=confirmed,
        date_skipped=skipped,
        rejected=rejected,
    )
