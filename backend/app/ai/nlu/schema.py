"""The labels the trained reader predicts. Training, evaluation and the API share this one list.

Intents are what the person wants. Slots are the exact pieces of the message that carry a value
(an amount, a currency, a date...). The model only marks spans of the original text; the
deterministic code in ``normalize.py`` turns a span into a typed value, so a number the person did
not type can never appear.
"""

from __future__ import annotations

# Order matters: the position is the class id inside the model file.
INTENTS: tuple[str, ...] = (
    "PLAN",  # "I need to pay GBP 10,000 tuition by 28 October": quote, rank, plan
    "CADENCE",  # "monthly or all at once for GBP 800 a month?": the send plan
    "COMPARE",  # "why is Provider B cheaper than A?"
    "CHARGES",  # OUR, SHA, BEN, short payment
    "DEADLINE",  # "when must I send it?"
    "CHECKLIST",  # documents
    "LIMITS",  # caps and limits
    "KYC",  # identity verification
    "STATUS",  # "where is my payment?"
    "DRAFT",  # "create a draft with Provider B"
    "REQUEST_APPROVAL",  # "request approval for this payment"
    "HELP",  # greetings, "what can you do?"
    "OUT_OF_SCOPE",  # a banking or general question this assistant does not handle
    "ATTACK",  # an instruction override, an action request, a secret request
)

SLOTS: tuple[str, ...] = ("AMOUNT", "CURRENCY", "DATE", "DURATION", "CHARGE", "PURPOSE", "PROVIDER")

# BIO tags: "O" is outside any slot, "B-X" starts a span of slot X, "I-X" continues it.
TAGS: tuple[str, ...] = ("O", *[f"{p}-{s}" for s in SLOTS for p in ("B", "I")])

INTENT_ID = {name: i for i, name in enumerate(INTENTS)}
TAG_ID = {name: i for i, name in enumerate(TAGS)}

# Intents that start or prepare something (a quote, a draft, an approval request). A message the
# reader files under OUT_OF_SCOPE or ATTACK must never end up here.
ACTION_INTENTS = frozenset({"PLAN", "CADENCE", "DRAFT", "REQUEST_APPROVAL"})

MAX_PIECES = 96  # a message is at most 1000 characters; the reader looks at the first 96 pieces
