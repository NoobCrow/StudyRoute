"""AI orchestrator: the pipeline of blueprint 14.2.

policy check -> facts from the engine -> PII masking -> model (or template) -> output guards
-> un-mask -> audit. The model can explain and propose; it can never act.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ai.context import ChatContext, gather_context
from app.ai.guards import GuardFailure, parse_llm_json, validate_llm_output
from app.ai.intents import Intent, choose_intent
from app.ai.llm import SYSTEM_PROMPT, LLMClient, LLMError
from app.ai.masking import Masker
from app.ai.number_guard import check_numbers
from app.ai.policy import PolicyResult, check_text
from app.ai.prompt import build_prompt
from app.ai.request_parser import parse_request
from app.ai.tasks import TaskResult, TaskRunner
from app.ai.templates import INDICATIVE, Responder, refusal
from app.api.context import AppContext
from app.core import errors
from app.core.crypto import sha256_ref
from app.domain.auth import ai_actor
from app.domain.constants import ActorType, Decision
from app.domain.rbac import Actor
from app.domain.rules import load_rules
from app.models import User

logger = logging.getLogger("studyroute.ai")
TEMPLATE_VERSION = "template-v1"
AI_USER_FALLBACK = "usr_ai_service"
DISCLAIMER = f"Sandbox. Synthetic data. {INDICATIVE}"
REMINDER = (
    "\n\nYour previous reply was rejected by a safety check ({code}). Reply again as JSON, "
    "using only numbers that appear in FACTS."
)
SAFE_FALLBACK = (
    "I could not build a reliable answer from the engine's numbers. Run a quote and ask again."
)


@dataclass
class Outcome:
    reply: str
    fact_ids: list[str]
    proposals: list[dict[str, Any]]
    status: str
    mode: str
    model: str
    failure: str | None = None
    retries: int = 0
    flags: list[str] = field(default_factory=list)


class Orchestrator:
    def __init__(self, ctx: AppContext, llm: LLMClient | None) -> None:
        self._ctx = ctx
        self._llm = llm
        self._tasks = TaskRunner(ctx)

    @property
    def mode(self) -> str:
        return "llm" if self._llm else "template"

    @property
    def model_version(self) -> str:
        return self._llm.model if self._llm else TEMPLATE_VERSION

    def _ai_actor(self, session: Session, human: Actor) -> Actor:
        parent = session.get(User, human.owner_id) if human.owner_id else None
        if parent is None:
            raise errors.Forbidden("The assistant works for a paying parent's household.")
        ai_user = session.execute(select(User).where(User.role == "ai")).scalars().first()
        return ai_actor(ai_user.id if ai_user else AI_USER_FALLBACK, parent)

    # --- the pipeline ---------------------------------------------------------------------
    def chat(
        self, actor: Actor, message: str, *, quote_id: str | None, payment_id: str | None
    ) -> dict[str, Any]:
        ctx = self._ctx
        text = message.strip()
        policy = check_text(text)  # 2. policy check: flag, never obey
        with ctx.db.read() as session:
            rules = load_rules(session)
            ai = self._ai_actor(session, actor)
        today = ctx.clock.now().astimezone(ZoneInfo("Asia/Dhaka")).date()
        parsed = parse_request(text, rules.supported_currencies(), today)
        intent = choose_intent(text, parsed, has_context=bool(quote_id or payment_id))
        task: TaskResult | None = None
        if intent in (Intent.PLAN, Intent.CADENCE) and not policy.blocked:
            task = self._tasks.run(
                ai, intent, parsed
            )  # a task: quote and plan, up to the human gate
            if task.quote_id:
                quote_id, payment_id = task.quote_id, None
        with ctx.db.read() as session:
            rules = load_rules(session)
            chat = gather_context(ctx, session, ai, rules, intent, quote_id, payment_id)  # 3. facts
        for key, label, value in task.facts if task else ():
            chat.facts.add(key, label, value)
        masker = Masker(chat.person_names)  # 4. mask personal data
        prompt = build_prompt(
            chat.facts,
            masker.mask(text),
            [masker.mask(e) for e in chat.excerpts],
            policy.flags,
            chat.ignored_documents,
        )
        responder = Responder(
            chat.facts, chat.provider_ids, text,
            quote_id=chat.quote_id, payment_id=chat.payment_id, legal=policy.legal_question,
        )  # fmt: skip
        responder.task = task
        outcome = self._decide(ai, intent, policy, chat, responder, prompt)
        reply = masker.unmask(outcome.reply)  # 8. un-mask
        if chat.ignored_documents:
            kinds = ", ".join(chat.ignored_documents)
            reply += (
                f" A document you uploaded ({kinds}) held instruction-like text, so I ignored it."
            )
            outcome.flags.append("DOCUMENT_INSTRUCTIONS_IGNORED")
        self._audit(ai, chat, policy, outcome, prompt, reply)
        used = [chat.facts.by_id(i) for i in outcome.fact_ids]
        return {
            "reply": reply,
            "facts_used": outcome.fact_ids,
            "facts": [{"id": f.id, "label": f.label, "value": f.value} for f in used if f],
            "guard": {
                "status": outcome.status,
                "flags": outcome.flags,
                "failure": outcome.failure,
                "retries": outcome.retries,
            },
            "proposed_actions": outcome.proposals,
            "task": task.card if task else None,
            "mode": outcome.mode,
            "model_version": outcome.model,
            "disclaimer": DISCLAIMER,
            "debug": {
                "masked_prompt": prompt,
                "note": "This is exactly what a model would see: masked, facts only.",
            },
        }

    def _decide(
        self, ai: Actor, intent: Any, policy: PolicyResult, chat: ChatContext,
        responder: Responder, prompt: str,
    ) -> Outcome:  # fmt: skip
        flags = list(policy.flags)
        if policy.blocked:
            answer = refusal(policy.flags)
            return Outcome(answer.reply, [], [], "policy_blocked", "template", TEMPLATE_VERSION,
                           ",".join(policy.flags), 0, flags)  # fmt: skip
        template = responder.answer(intent)
        if self._llm is None:
            return self._from_template(template, chat, "passed", None, 0, flags)
        failure, retries = "", 0
        for attempt in range(2):
            retries = attempt
            user_prompt = prompt if attempt == 0 else prompt + REMINDER.format(code=failure)
            try:
                result = self._llm.complete(system=SYSTEM_PROMPT, user=user_prompt)
                valid = validate_llm_output(
                    parse_llm_json(result.text), facts=chat.facts, actor=ai,
                    legal_question=policy.legal_question,
                )  # fmt: skip
            except GuardFailure as exc:  # 6./7. number guard, tool guard, claims
                failure = exc.code
                logger.info("model reply rejected: %s", exc.code)
                continue
            except LLMError as exc:
                logger.warning("model unavailable: %s", exc)
                return self._from_template(
                    template, chat, "llm_unavailable", "LLM_UNAVAILABLE", 0, flags
                )
            proposals = self._complete_proposals(valid.proposals, chat)
            return Outcome(valid.reply, valid.facts_used, proposals, "passed", "llm", result.model,
                           None, retries, flags)  # fmt: skip
        return self._from_template(template, chat, "template_fallback", failure, retries, flags)

    def _from_template(
        self, answer: Any, chat: ChatContext, status: str, failure: str | None, retries: int,
        flags: list[str],
    ) -> Outcome:  # fmt: skip
        check = check_numbers(answer.reply, chat.facts.numbers())
        reply = answer.reply if check.ok else SAFE_FALLBACK
        ids = [f.id for k in answer.keys if (f := chat.facts.get(k))]
        return Outcome(reply, ids if check.ok else [], answer.proposals, status, "template",
                       TEMPLATE_VERSION, failure, retries, flags)  # fmt: skip

    @staticmethod
    def _complete_proposals(
        proposals: list[dict[str, Any]], chat: ChatContext
    ) -> list[dict[str, Any]]:
        """Bind proposals to the conversation's own quote/payment and list what a human must add."""
        done: list[dict[str, Any]] = []
        for proposal in proposals:
            args = dict(proposal["args"])
            if proposal["tool"] == "create_draft":
                if (
                    chat.quote_id is None
                    or args.setdefault("quote_id", chat.quote_id) != chat.quote_id
                ):
                    continue
                proposal["missing"] = [a for a in ("recipient_id", "reference") if a not in args]
            elif (
                chat.payment_id is None
                or args.setdefault("payment_id", chat.payment_id) != chat.payment_id
            ):
                continue
            proposal["args"] = args
            done.append(proposal)
        return done

    def _audit(
        self,
        ai: Actor,
        chat: ChatContext,
        policy: PolicyResult,
        outcome: Outcome,
        prompt: str,
        reply: str,
    ) -> None:  # fmt: skip
        ctx = self._ctx
        problems = [outcome.failure] if outcome.failure else []
        blocked = policy.blocked or outcome.status != "passed" or bool(chat.ignored_documents)
        reasons = (
            problems
            + list(policy.flags)
            + (["DOCUMENT_INSTRUCTIONS_IGNORED"] if chat.ignored_documents else [])
        )
        base = {
            "actor_type": ActorType.AI, "actor_id": ai.user_id,
            "payment_id": chat.payment_id, "quote_id": chat.quote_id,
        }  # fmt: skip
        with ctx.db.write() as session:
            ctx.audit.append(
                session, **base,
                action="ai.blocked" if blocked else "ai.reply",
                decision=Decision.BLOCKED if blocked else None,
                reason_code=",".join(dict.fromkeys(reasons))[:64] or None,
                detail=f"for {ai.owner_id}; status={outcome.status}; mode={outcome.mode}",
                input_hash=sha256_ref(prompt), output_hash=sha256_ref(reply),
                model_version=outcome.model,
            )  # fmt: skip
            for proposal in outcome.proposals:
                ctx.audit.append(
                    session, **base,
                    action="ai.tool_proposed", decision=Decision.SUGGESTED,
                    reason_code=proposal["tool"],
                    detail=f"for {ai.owner_id}; {proposal['tool']} {proposal['args']}"[:240],
                    model_version=outcome.model,
                )  # fmt: skip
