"""PII masking before any text reaches an LLM (blueprint 14.5).

Names become numbered tokens, accounts show country and last four only, passports, e-mails
and phone numbers are removed. The mapping stays on the server and is used to un-mask replies.
"""

from __future__ import annotations

import re
from collections.abc import Iterable

from app.engine.validators import last4

_EMAIL = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)+")
_PHONE = re.compile(r"\+\d[\d\s().-]{7,}\d")
_IBAN = re.compile(r"\b[A-Z]{2}\d{2}(?: ?[A-Z0-9]{4}){2,7}(?: ?[A-Z0-9]{1,3})?\b")
_PASSPORT = re.compile(r"\b[A-Z]{1,2}\d{6,9}\b")
_LONG_DIGITS = re.compile(r"(?<![\w.])\d(?: ?\d){7,18}(?![\w])")


class Masker:
    def __init__(self, person_names: Iterable[str] = ()) -> None:
        names = {n.strip() for n in person_names if n and len(n.strip()) >= 3}
        self._names = sorted(names, key=len, reverse=True)
        self._persons: dict[str, str] = {}
        self._accounts: dict[str, str] = {}

    def _person_token(self, name: str) -> str:
        for token, original in self._persons.items():
            if original.lower() == name.lower():
                return token
        token = f"[PERSON_{len(self._persons) + 1}]"
        self._persons[token] = name
        return token

    def _account_token(self, display: str) -> str:
        token = f"[ACCT_{len(self._accounts) + 1}]"
        self._accounts[token] = display
        return token

    def mask(self, text: str) -> str:
        masked = _EMAIL.sub("[EMAIL_REMOVED]", text)
        masked = _PHONE.sub("[PHONE_REMOVED]", masked)
        masked = _IBAN.sub(
            lambda m: self._account_token(f"{m.group()[:2]}** **** {last4(m.group())}"), masked
        )
        masked = _PASSPORT.sub("[ID_REMOVED]", masked)
        masked = _LONG_DIGITS.sub(lambda m: self._account_token(f"**** {last4(m.group())}"), masked)
        if self._names:
            # one pass, so tokens are numbered in order of first appearance in the text
            pattern = re.compile("|".join(re.escape(n) for n in self._names), re.I)
            masked = pattern.sub(lambda m: self._person_token(self._canonical(m.group())), masked)
        return masked

    def _canonical(self, matched: str) -> str:
        return next(n for n in self._names if n.lower() == matched.lower())

    def unmask(self, text: str) -> str:
        restored = text
        for token, original in self._persons.items():
            restored = restored.replace(token, original)
        for token, display in self._accounts.items():
            restored = restored.replace(token, display)
        return restored
