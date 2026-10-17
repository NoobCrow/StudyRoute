"""Gather the FACTS for one chat turn. Read-only, and every read goes through the AI's own
permissions (the same checks a human call would face)."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from typing import Any

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.ai import facts_builder as fb
from app.ai.facts import FactSet
from app.ai.intents import Intent
from app.ai.policy import check_text
from app.ai.student_topic import StudentTopic
from app.api.context import AppContext
from app.domain.constants import RecipientType
from app.domain.rbac import Actor, Perm, authorize
from app.domain.rules import Rules
from app.domain.stress import DEFAULT_DROPS, stress_quote
from app.domain.student_guide import arrival_guide
from app.engine.planner import plan_deadline
from app.models import Recipient, User

EXCERPT_CHARS = 500
MAX_DOCUMENTS = 3


@dataclass
class ChatContext:
    facts: FactSet
    provider_ids: list[str]
    person_names: list[str]
    quote_id: str | None = None
    payment_id: str | None = None
    excerpts: list[str] = field(default_factory=list)
    ignored_documents: list[str] = field(default_factory=list)


def _household_names(session: Session, owner_id: str) -> list[str]:
    rows = session.execute(
        select(User.display_name).where(or_(User.id == owner_id, User.parent_id == owner_id))
    )
    return [name for (name,) in rows]


def gather_context(
    ctx: AppContext,
    session: Session,
    ai: Actor,
    rules: Rules,
    intent: Intent,
    quote_id: str | None,
    payment_id: str | None,
    drops: Sequence[Decimal] = DEFAULT_DROPS,
    topic: StudentTopic | None = None,
) -> ChatContext:
    owner = ai.owner_id or ""
    facts = FactSet()
    fb.build_rule_facts(facts, rules)
    chat = ChatContext(facts, rules.provider_ids(), _household_names(session, owner))
    due: date | None = None
    country, purpose = "GB", "TUITION"
    if payment_id:
        payment = ctx.payments.load(session, ai, payment_id)
        view = ctx.payments.view(session, rules, payment)
        fb.build_payment_facts(facts, view)
        quote_id, due, chat.payment_id = payment.quote_id, payment.due_date, payment.id
        recipient = session.get(Recipient, payment.recipient_id)
        if recipient is not None and recipient.type == RecipientType.STUDENT.value:
            chat.person_names.append(recipient.display_name)
    if quote_id:
        quote: dict[str, Any] = ctx.quotes.get(session, ai, quote_id)
        fb.build_quote_facts(facts, quote)
        if intent is Intent.STRESS:
            fb.build_stress_facts(facts, stress_quote(rules, quote, drops=drops))
        chat.quote_id = quote["quote_id"]
        country, purpose = quote["destination_country"], quote["purpose"]
        if due is None and quote["due_date"]:
            due = date.fromisoformat(quote["due_date"])
    if due is not None:
        authorize(ai, Perm.PLANNER_READ)
        plan = plan_deadline(
            due_date=due,
            now=ctx.clock.now(),
            calendars=rules.calendars(country),
            params=rules.planner_params(),
        )
        fb.build_plan_facts(facts, plan.to_api_dict(), rules.corridor(country).name)
    if intent is Intent.CHECKLIST or (intent is Intent.PLAN and quote_id):
        authorize(ai, Perm.CHECKLIST_READ)
        fb.build_checklist_facts(facts, rules.checklist(country, purpose))
    if intent is Intent.COSTS:
        authorize(ai, Perm.PLANNER_READ)
        fb.build_student_cost_facts(facts, rules, topic or StudentTopic(None, None, None, "shared"))
    if intent is Intent.ARRIVAL:
        authorize(ai, Perm.PLANNER_READ)
        named = topic.country if topic else None
        fb.build_arrival_facts(
            facts, arrival_guide(rules, named or (country if quote_id else None))
        )
    fb.build_kyc_facts(facts, ctx.kyc.view(session, ai, rules))
    _collect_documents(ctx, session, ai, chat)
    return chat


def _collect_documents(ctx: AppContext, session: Session, ai: Actor, chat: ChatContext) -> None:
    for doc in ctx.documents.list(session, ai, chat.payment_id)[:MAX_DOCUMENTS]:
        if not doc.content_text:
            continue
        if check_text(doc.content_text).blocked:
            chat.ignored_documents.append(doc.kind)  # looks like instructions: never forwarded
        else:
            chat.excerpts.append(f"{doc.kind}: {doc.content_text[:EXCERPT_CHARS]}")
