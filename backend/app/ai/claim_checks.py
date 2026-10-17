"""Conservative multilingual regression checks; not a general semantic truth verifier."""

from __future__ import annotations

import re

from app.ai.facts import FactSet
from app.ai.number_guard import allowed_numbers, numbers_in

# Future success claims are unnecessary in a read-only explainer. Reject them even when
# surrounded by a later caveat; retry may use clear non-guarantee wording instead.
_PROMISE = re.compile(
    r"\b(?:will|shall)\s+(?:(?:automatically|definitely|certainly|surely)\s+)*"
    r"(?:be\s+)?(?:approved|authori[sz]ed|sent|settled|delivered|released)\b"
    r"|\b(?:guarantees?|ensures?)\s+(?:(?:your|the|a|payment)\s+)*approval\b"
    r"|(?:পেমেন্ট|পেমেন্টের|পেমেন্টটি|ট্রান্সফার|অর্থ|টাকা)[^।.!?\n]{0,65}"
    r"(?:অনুমোদন\s*(?:হবে|হয়ে যাবে|হয়ে যাবে|পাবে)|অনুমোদিত\s*(?:হবে|হয়ে যাবে|হয়ে যাবে)|পৌঁছে যাবে)"
    r"|\b(?:payment|transfer)\b[^.!?\n]{0,55}\b(?:approve|approved)\s+(?:hobe|hoye\s+jabe)\b",
    re.I,
)
_BN_ACTION = re.compile(
    r"আমি[^।.!?\n]{0,40}(?:অনুমোদন করেছি|অনুমোদন করে দিয়েছি|অনুমোদন করে দিয়েছি|"
    r"পাঠিয়ে দিয়েছি|পাঠিয়ে দিয়েছি)"
)
_CAP = re.compile(r"\b(?:caps?|limits?)\b|সীমা|লিমিট", re.I)
_SANDBOX = re.compile(r"sandbox|স্যান্ডবক্স|স্যাণ্ডবক্স", re.I)
_NOT_LEGAL = re.compile(
    r"not\s+(?:(?:a|the|your)\s+)?(?:legal|bank)|not[^.!?\n]{0,25}legal"
    r"|(?:আইনি|আইনগত|ব্যাংক)[^।.!?\n]{0,35}(?:নয়|নয়|না)"
    r"|(?:aini|bank)[^.!?\n]{0,25}(?:noy|noi|na)",
    re.I,
)


def claim_failure(reply: str, facts: FactSet) -> str | None:
    for match in _PROMISE.finditer(reply):
        before, after = reply[: match.start()], reply[match.end() :]
        if re.search(r"(?:not|cannot|never)\s+$", before, re.I):
            continue
        if re.match(r"\s*(?:না|নয়|নয়)(?:[।.!?\s]|$)", after):
            continue
        return "APPROVAL_PROMISE"
    if _BN_ACTION.search(reply):
        return "APPROVAL_PROMISE"
    if not facts.has("kyc.status") and re.search(
        r"\b(?:NEEDS_DOCUMENTS|KYC_VERIFIED|KYC_REJECTED)\b"
        r"|\byour\s+(?:mock\s+)?(?:kyc|identity)\s+(?:status\s+)?(?:is|needs|requires)\b"
        r"|আপনার\s*(?:mock\s*)?(?:KYC|কেওয়াইসি|কেওয়াইসি)\s*(?:status|স্ট্যাটাস|অবস্থা)",
        reply,
        re.I,
    ):
        return "UNSUPPORTED_ACCOUNT_STATUS"
    # Check each cap-containing sentence, not an unrelated disclaimer elsewhere.
    if facts.keys_with_prefix("limit."):
        cap_numbers = allowed_numbers(f.value for f in facts.all() if f.key.startswith("limit."))
        for sentence in re.split(r"[।!?\n]|\.(?!\d)", reply):
            if (_CAP.search(sentence) or cap_numbers.intersection(numbers_in(sentence))) and (
                not _SANDBOX.search(sentence) or not _NOT_LEGAL.search(sentence)
            ):
                return "UNQUALIFIED_SANDBOX_CAP"
    return None
