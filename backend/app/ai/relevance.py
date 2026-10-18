"""Minimise current account facts forwarded to cloud conversation turns."""

from __future__ import annotations

from dataclasses import replace

from app.ai.context import ChatContext
from app.ai.intents import Intent


def relevant_context(chat: ChatContext, intent: Intent) -> ChatContext:
    # Financial tasks keep engine inputs; greetings/identity/app-help need no account data.
    prefixes = {
        Intent.HELP: (),
        Intent.KYC: ("kyc.",),
        Intent.LIMITS: ("limit.", "bd."),
        Intent.DEADLINE: ("plan.", "quote.target"),
        Intent.CHECKLIST: ("checklist.",),
    }.get(intent)
    if prefixes is None:
        return chat
    return replace(chat, facts=chat.facts.selected(prefixes), excerpts=[])
