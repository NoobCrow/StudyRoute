"""Turn what the assistant just understood into the state the dialogue policy decides from."""

from __future__ import annotations

from app.ai.dialogue.state import DialogueState, SlotState
from app.ai.intents import Intent
from app.ai.nlu.understanding import Pending, Understanding

_MISSING = SlotState()


def build_state(understanding: Understanding, pending: Pending | None) -> DialogueState:
    """The state after reading a message, with the history of the task so far (``pending``)."""
    held = understanding.evidence
    amount = held.get("amount", _MISSING)
    extra = understanding.amount_candidates >= 2 or (
        pending is not None
        and pending.extra_amount
        and amount.source == "earlier"
        and not understanding.confirmed
    )
    return DialogueState(
        task="CADENCE" if understanding.intent is Intent.CADENCE else "PLAN",
        amount=amount,
        date=held.get("date", _MISSING),
        months=held.get("months", _MISSING),
        intent_confidence=understanding.confidence or 1.0,
        confirmed=understanding.confirmed,
        date_skipped=understanding.date_skipped or bool(pending and pending.date_skipped),
        turns=pending.turns if pending else 0,
        extra_amount=extra and not understanding.confirmed,
        asked=pending.asked if pending else (False, False, False),
    )
