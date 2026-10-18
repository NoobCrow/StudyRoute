"""Is a rewrite of the engine's draft faithful to it?

The small model rewords the engine's draft, putting the answer first when the draft has it.
These plain checks decide whether the rewrite may be used. They run in three places, so a rewrite
is judged the same way everywhere: when the training targets are chosen (only verified rewrites
are learned from), when the model is evaluated, and live, in front of the assistant's own guards.
A rewrite that fails any check is thrown away and the engine's draft is shown instead."""

from __future__ import annotations

import re
from dataclasses import dataclass

from app.ai.guards import _ACTION_CLAIM, _HEDGE, _LEGAL_CLAIM
from app.ai.number_guard import numbers_in
from app.ai.templates import INDICATIVE

MIN_WORDS = 4
MAX_WORDS = 150
MIN_KEPT_FIGURES = 0.6  # a rewrite may drop figures the question did not need, but not most of them

_UNQUALIFIED_PROVIDER = re.compile(r"\bProvider [A-Z]\b(?! \(synthetic\))")
_PROMISE = re.compile(r"\b(?:guarantee[sd]?|promise[sd]?|definitely will|for sure)\b", re.I)
_REFUSAL = re.compile(
    r"\b(?:cannot|can't|can not|unable|do not have|don't have|only you|not verified|a human)\b",
    re.I,
)
_BENGALI = re.compile(r"[ঀ-৿]")


@dataclass(frozen=True)
class Verdict:
    ok: bool
    reason: str = ""


def _figures(text: str) -> set:
    return set(numbers_in(text))


def check_rewrite(draft: str, rewrite: str) -> Verdict:
    """Accept the rewrite only if it keeps the draft's facts and adds nothing."""
    words = len(rewrite.split())
    # A long draft (a payment plan, a checklist) may need a long answer; the limit grows with it.
    longest = max(MAX_WORDS, int(len(draft.split()) * 1.2) + 10)
    if not MIN_WORDS <= words <= longest:
        return Verdict(False, "LENGTH")
    if _BENGALI.search(rewrite) and not _BENGALI.search(draft):
        return Verdict(False, "LANGUAGE")
    allowed, found = _figures(draft), _figures(rewrite)
    if not found <= allowed:
        return Verdict(False, "NEW_FIGURE")
    if allowed and len(found & allowed) < MIN_KEPT_FIGURES * len(allowed):
        return Verdict(False, "DROPPED_FIGURES")
    if _UNQUALIFIED_PROVIDER.search(rewrite):
        return Verdict(False, "PROVIDER_NAME")
    if INDICATIVE in draft and INDICATIVE not in rewrite:
        return Verdict(False, "DISCLAIMER_LOST")
    if _ACTION_CLAIM.search(rewrite):
        return Verdict(False, "ACTION_CLAIM")
    if _LEGAL_CLAIM.search(_HEDGE.sub(" ", rewrite)):
        return Verdict(False, "LEGAL_CLAIM")
    if _PROMISE.search(rewrite) and not _PROMISE.search(draft):
        return Verdict(False, "PROMISE")
    if _REFUSAL.search(draft) and not _REFUSAL.search(rewrite):
        return Verdict(False, "REFUSAL_LOST")
    return Verdict(True)
