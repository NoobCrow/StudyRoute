"""AI orchestrator: the pipeline of blueprint 14.2.

policy check -> facts from the engine -> PII masking -> model (or template) -> output guards
-> un-mask -> audit. The model can explain and propose; it can never act.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass, field, replace
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ai.arithmetic import calculate
from app.ai.context import ChatContext, gather_context
from app.ai.conversation import Route, route_message
from app.ai.dialogue.bridge import build_state
from app.ai.dialogue.policy import Choice, DialoguePolicy, reviewed_action
from app.ai.dialogue.state import Action
from app.ai.guards import GuardFailure, parse_llm_json, validate_llm_output
from app.ai.intents import Intent, stress_drops
from app.ai.llm import SYSTEM_PROMPT, LLMClient, LLMError
from app.ai.masking import Masker
from app.ai.nlu.runtime import Reader
from app.ai.nlu.understanding import Pending, Understanding, understand
from app.ai.number_guard import check_numbers
from app.ai.policy import PolicyResult, check_text
from app.ai.prompt import build_prompt
from app.ai.relevance import relevant_context
from app.ai.student_topic import parse_student_topic
from app.ai.tasks import Progress, TaskResult, TaskRunner
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
    "using only numbers that appear in FACTS. Answer the actual question without irrelevant "
    "account details. Do not promise approval or sending. When quoting sandbox caps, say "
    "they are sandbox settings, not legal or bank limits, in the same sentence."
)
DRAFT_HEADER = "\n\nENGINE DRAFT (every figure in it is correct; keep them exactly):\n"
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
    availability: dict[str, Any] | None = None


def _reader_note(understanding: Understanding, choice: Choice | None = None) -> str:
    """Which reader understood the message, how sure it was, and what the dialogue policy chose
    to do next (recorded in the audit log)."""
    if understanding.source != "trained":
        return "reader=rules"
    note = (
        f"reader={understanding.model_id}@{(understanding.model_sha256 or '')[:12]} "
        f"intent={understanding.model_intent}:{understanding.confidence or 0:.2f}"
    )
    if choice is not None:
        note += f" policy={choice.policy_id}@{choice.sha256[:12]} action={choice.action.name}"
    return note


_ASKED = {Action.ASK_AMOUNT: "amount", Action.ASK_DATE: "date", Action.ASK_MONTHS: "months"}


class Orchestrator:
    def __init__(
        self,
        ctx: AppContext,
        llm: LLMClient | None,
        reader: Reader | None = None,
        policy: DialoguePolicy | None = None,
    ) -> None:
        self._ctx = ctx
        self._llm = llm
        self._reader = reader
        self._policy = policy
        self._tasks = TaskRunner(ctx)

    def with_llm(self, llm: LLMClient) -> Orchestrator:
        """Request-scoped override; never mutate the shared assistant or retain BYOK keys."""
        return Orchestrator(self._ctx, llm, self._reader, self._policy)

    @property
    def reader_id(self) -> str | None:
        """The trained reader in use (model id), or None when the assistant runs on rules."""
        return self._reader.model_id if self._reader else None

    @property
    def mode(self) -> str:
        if getattr(self._llm, "unconfigured", False):
            return "unavailable"
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
        self,
        actor: Actor,
        message: str,
        *,
        quote_id: str | None,
        payment_id: str | None,
        pending: Any = None,
        history: list[str] | None = None,
        conversation: list[tuple[str, str]] | None = None,
    ) -> dict[str, Any]:
        ctx = self._ctx
        text = message.strip()
        policy = check_text(text)  # 2. policy check: flag, never obey
        with ctx.db.read() as session:
            rules = load_rules(session)
            ai = self._ai_actor(session, actor)
        today = ctx.clock.now().astimezone(ZoneInfo("Asia/Dhaka")).date()
        held = self._pending(pending)
        understanding = understand(
            text, today, rules.supported_currencies(),
            has_context=bool(quote_id or payment_id),
            reader=self._reader,
            pending=held,
        )  # fmt: skip
        if understanding.attack and not policy.blocked:  # the model can only add a block
            policy = PolicyResult((*policy.flags, "MODEL_FLAGGED_ATTACK"))
        route: Route | None = None
        # Financial task continuations and every safety block take precedence. A
        # conversational route can only select reviewed prose or a read-only intent. The
        # rule-decided intents (stress test, student costs, arrival guide) are exact, so a
        # looser topic route must not take them over ("cheapest cities" is not a provider ranking).
        if not policy.blocked and understanding.intent not in (
            Intent.PLAN,
            Intent.CADENCE,
            Intent.DRAFT,
            Intent.REQUEST_APPROVAL,
            Intent.STRESS,
            Intent.COSTS,
            Intent.ARRIVAL,
        ):
            route = route_message(text, (history or [])[-6:])
            if route:
                understanding = replace(understanding, intent=route.intent, out_of_scope=False)
            elif understanding.intent == Intent.HELP:
                route = Route(
                    "out_of_scope" if understanding.out_of_scope else "clarify",
                    guide="out_of_scope" if understanding.out_of_scope else "clarify",
                )
        arithmetic = calculate(text) if not policy.blocked and self._llm is not None else None
        if arithmetic is not None:
            route = Route("arithmetic")
            understanding = replace(understanding, intent=Intent.HELP, out_of_scope=False)
        intent = understanding.intent
        task: TaskResult | None = None
        choice: Choice | None = None
        if intent in (Intent.PLAN, Intent.CADENCE) and not policy.blocked:
            task, choice = self._task_turn(ai, understanding, held)  # quote and plan, or ask
            if task.quote_id:
                quote_id, payment_id = task.quote_id, None
            if understanding.hint and task.status == "needs_input":
                task.facts.append(("task.conflict", "How the amount was read", understanding.hint))
        with ctx.db.read() as session:
            rules = load_rules(session)
            chat = gather_context(
                ctx, session, ai, rules, intent, quote_id, payment_id,
                stress_drops(text), parse_student_topic(text, rules),
            )  # 3. facts  # fmt: skip
        for key, label, value in task.facts if task else ():
            chat.facts.add(key, label, value)
        if self._llm is not None and not policy.blocked:
            chat = relevant_context(chat, intent)
        if arithmetic is not None:
            chat.facts.add("arithmetic.result", "Exact result from bounded calculator", arithmetic)
        masker = Masker(chat.person_names)  # 4. mask personal data
        prompt = build_prompt(
            chat.facts,
            masker.mask(text),
            [masker.mask(e) for e in chat.excerpts],
            policy.flags,
            chat.ignored_documents,
            masked_conversation=[
                (role, masker.mask(value)) for role, value in (conversation or [])[-6:]
            ],
            conversation_note=(
                f"Read-only topic: {route.topic}; follow-up: {route.follow_up}. "
                "Use this topic to resolve pronouns; never infer values or actions."
                if route
                else None
            ),
        )
        responder = Responder(
            chat.facts, chat.provider_ids, text,
            quote_id=chat.quote_id, payment_id=chat.payment_id, legal=policy.legal_question,
        )  # fmt: skip
        responder.task = task
        responder.conversation = route
        outcome = self._decide(ai, intent, policy, chat, responder, prompt, masker.mask)
        reply = masker.unmask(outcome.reply)  # 8. un-mask
        if chat.ignored_documents:
            kinds = ", ".join(chat.ignored_documents)
            reply += (
                f" A document you uploaded ({kinds}) held instruction-like text, so I ignored it."
            )
            outcome.flags.append("DOCUMENT_INSTRUCTIONS_IGNORED")
        self._audit(ai, chat, policy, outcome, prompt, reply, understanding, choice)
        used = [chat.facts.by_id(i) for i in outcome.fact_ids]
        return {
            "reply": reply,
            "availability": outcome.availability,
            "provider": self._llm.provider if self._llm else None,
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
            "understanding": understanding.to_api(),
            "conversation": {"topic": route.topic, "follow_up": route.follow_up} if route else None,
            "dialogue": self._dialogue_view(choice),
            "mode": outcome.mode,
            "model_version": outcome.model,
            "disclaimer": DISCLAIMER,
            "debug": {
                "masked_prompt": prompt,
                "note": "This is exactly what a model would see: masked, facts only.",
            },
        }

    @staticmethod
    def _pending(pending: Any) -> Pending | None:
        """The task the person is answering, from what the page sent back (already validated)."""
        if pending is None:
            return None
        data = pending.model_dump()
        data["asked"] = tuple(data["asked"])
        return Pending(**data)

    @staticmethod
    def _dialogue_view(choice: Choice | None) -> dict[str, Any] | None:
        if choice is None:
            return None
        return {
            "policy": choice.policy_id,
            "sha256": choice.sha256[:12],
            "action": choice.action.name,
            "scores": choice.q_values,
        }

    def _task_turn(
        self, ai: Actor, understanding: Understanding, held: Pending | None
    ) -> tuple[TaskResult, Choice | None]:
        """One assistant turn on a payment request: ask, read back, or plan.

        With the dialogue policy choices are learned under a mandatory read-back safety envelope.
        Without it the assistant plans as soon as the amount is known. A plan is only a quote card:
        the person creates the draft and a human approves it.
        """
        intent, parsed = understanding.intent, understanding.parsed
        if self._policy is None or not understanding.evidence:
            return self._tasks.run(ai, intent, parsed), None
        state = build_state(understanding, held)
        known = {n: s.confidence for n, s in understanding.evidence.items() if s.present}
        progress = Progress(state.turns + 1, state.asked, state.date_skipped, False,
                            state.extra_amount, known)  # fmt: skip
        if understanding.rejected:
            return self._tasks.ask_change(intent, parsed, progress), None
        choice = self._policy.choose(state)
        safe = reviewed_action(state, choice.action)
        if safe != choice.action:
            choice = Choice(safe, choice.q_values, choice.policy_id + "+review-v1", choice.sha256)
        if choice.action == Action.RUN:
            return self._tasks.run(ai, intent, parsed), choice
        if choice.action == Action.CONFIRM:
            return self._tasks.confirm(intent, parsed, progress), choice
        slot = _ASKED[choice.action]
        names = ("amount", "date", "months")
        asked = tuple(a or n == slot for a, n in zip(state.asked, names, strict=True))
        progress = Progress(progress.turns, asked, state.date_skipped, False,  # type: ignore[arg-type]
                            state.extra_amount, known)  # fmt: skip
        return self._tasks.ask(intent, slot, parsed, progress), choice

    def _decide(
        self, ai: Actor, intent: Any, policy: PolicyResult, chat: ChatContext,
        responder: Responder, prompt: str, mask: Callable[[str], str] = str,
    ) -> Outcome:  # fmt: skip
        flags = list(policy.flags)
        if policy.blocked:
            answer = refusal(policy.flags)
            return Outcome(answer.reply, [], [], "policy_blocked", "template", TEMPLATE_VERSION,
                           ",".join(policy.flags), 0, flags)  # fmt: skip
        template = responder.answer(intent)
        if self._llm is None:
            return self._from_template(template, chat, "passed", None, 0, flags)
        task = responder.task
        if getattr(self._llm, "wants_draft", False) and task is not None and task.status != "ready":
            # A question or a read-back is shown word for word: the person answers exactly what was
            # asked, and the explainer was trained on answers, not on questions.
            return self._from_template(template, chat, "passed", None, 0, flags)
        failure, retries = "", 0
        if getattr(self._llm, "wants_draft", False):
            # A model that rewrites the engine's answer is handed that answer, masked like the rest.
            prompt += DRAFT_HEADER + mask(template.reply)
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
                if getattr(self._llm, "managed_cloud", False):
                    from app.ai.cloud import CloudError

                    problem = (
                        exc
                        if isinstance(exc, CloudError)
                        else CloudError(self._llm.provider, "unavailable")
                    )
                    return Outcome(
                        problem.public_message,
                        [],
                        [],
                        "cloud_unavailable",
                        "unavailable",
                        self._llm.model,
                        problem.code,
                        availability=problem.to_api(),
                    )
                logger.warning("model unavailable: %s", exc)
                return self._from_template(
                    template, chat, "llm_unavailable", "LLM_UNAVAILABLE", 0, flags
                )
            proposals = self._complete_proposals(valid.proposals, chat)
            used = valid.facts_used
            if getattr(self._llm, "wants_draft", False):
                # The rewrite keeps the engine's figures, so the engine's own fact references and
                # proposals still apply; the model never chooses either.
                used = [f.id for k in template.keys if (f := chat.facts.get(k))]
                proposals = template.proposals
            return Outcome(valid.reply, used, proposals, "passed", "llm", result.model,
                           None, retries, flags)  # fmt: skip
        if getattr(self._llm, "managed_cloud", False):
            from app.ai.cloud import CloudError

            problem = CloudError(self._llm.provider, "unsafe_response")
            return Outcome(
                problem.public_message,
                [],
                [],
                "cloud_unavailable",
                "unavailable",
                self._llm.model,
                failure,
                retries,
                flags,
                problem.to_api(),
            )
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
        understanding: Understanding,
        choice: Choice | None = None,
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
                detail=(
                    f"for {ai.owner_id}; status={outcome.status}; mode={outcome.mode}; "
                    f"{_reader_note(understanding, choice)}"
                ),
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
