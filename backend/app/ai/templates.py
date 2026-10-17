"""Deterministic answers (template mode). Used when no LLM is configured or a guard fails.

Every number is looked up in the FACTS; nothing is calculated here.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from app.ai.conversation import GUIDES, Route
from app.ai.facts import FactSet
from app.ai.intents import Intent, mentioned_providers
from app.ai.number_guard import numbers_in

INDICATIVE = "Indicative. Confirm with your AD bank."
SANDBOX_NOTE = "This is a sandbox with synthetic numbers, so treat it as indicative."
EXAMPLE_CADENCE_HINT = "How often should I send GBP 800 a month for 9 months?"
NO_QUOTE = (
    "I do not have a quote to work from. Run a quote on the Compare screen and I will explain it."
)
COST_WORDS = (
    ("rent", "rent"),
    ("food", "food and groceries"),
    ("transport", "transport"),
    ("utilities", "bills"),
    ("phone_internet", "phone and internet"),
    ("other", "study materials and leisure"),
)
ARRIVAL_STAGES = (
    ("before", "Before you fly"),
    ("first_week", "In your first week"),
    ("first_month", "In your first month"),
)


@dataclass
class Answer:
    reply: str
    keys: list[str] = field(default_factory=list)
    proposals: list[dict[str, Any]] = field(default_factory=list)


REFUSALS = {
    "INSTRUCTION_OVERRIDE": "I follow fixed safety rules and I cannot drop them, whatever the message or document says.",
    "ACTION_REQUEST": "I cannot approve, submit, cancel or change any payment. A human parent must do that in the app, with a fresh MFA step.",
    "LIMIT_CHANGE": "I cannot change limits. An admin changes rules on the Rules screen, and every change is audited.",
    "CONFIG_CHANGE": "I cannot change rules or settings. An admin does that on the Rules screen, and every change is audited.",
    "PRIVILEGE_CLAIM": "I cannot act on claims about who someone is. Permissions come from the signed-in account only.",
    "SECRET_REQUEST": "I cannot share my instructions, secrets, tokens or another person's account details.",
    "FABRICATION_REQUEST": "I do not make up numbers. If I do not have a figure, I will say so and suggest running a quote.",
    "MODEL_FLAGGED_ATTACK": "That reads like an instruction to drop my rules or to act for you, which I cannot do. Nothing was changed; a human parent approves in the app, with a fresh MFA step.",
}


def refusal(flags: tuple[str, ...]) -> Answer:
    parts = [REFUSALS[f] for f in REFUSALS if f in flags]
    parts.append("I can explain the engine's numbers, the charge codes, deadlines and documents.")
    if "LEGAL_QUESTION" in flags:
        parts.append(f"I cannot say whether something is legal or within a limit. {INDICATIVE}")
    return Answer(" ".join(parts))


class Responder:
    def __init__(
        self, facts: FactSet, provider_ids: list[str], message: str, *,
        quote_id: str | None, payment_id: str | None, legal: bool = False,
    ) -> None:  # fmt: skip
        self.facts = facts
        self.provider_ids = provider_ids
        self.message = message
        self.quote_id = quote_id
        self.payment_id = payment_id
        self.legal = legal
        self.conversation: Route | None = None
        self.used: list[str] = []
        self.task: Any = None  # set by the orchestrator when a task ran

    # --- helpers ------------------------------------------------------------------------
    def v(self, key: str) -> str:
        fact = self.facts.get(key)
        if fact is None:
            return ""
        if key not in self.used:
            self.used.append(key)
        return fact.value

    def _have_quote(self) -> bool:
        return self.facts.has("quote.target") and bool(self.provider_ids)

    def _ranked(self) -> list[str]:
        ids = [p for p in self.provider_ids if self.facts.has(f"{p}.rank")]
        return sorted(ids, key=lambda p: int(self.facts.value(f"{p}.rank")))

    def _deadline_pick(self, ranked: list[str]) -> str:
        """The provider to propose: the cheapest that arrives in time, else the fastest."""
        if self.facts.has("deadline.best_id"):
            return self.facts.value("deadline.best_id")
        if self.facts.has("deadline.fastest_id"):
            return self.facts.value("deadline.fastest_id")
        return ranked[0]

    def _lowest_cost_sentence(self, ranked: list[str], best: str) -> str:
        cost = (
            f"{self.v(f'{best}.name')} at {self.v(f'{best}.cost_pct')} of the amount, "
            f"{self.v(f'{best}.total_cost')} in total. You would pay {self.v(f'{best}.parent_pays')}."
        )
        if not self.facts.has("deadline.cheapest_misses"):
            return f"The lowest true cost is {cost}"
        if not self.facts.has("deadline.best_id"):
            return (
                f"No provider can arrive by {self.v('deadline.due_date')} if the money is sent on "
                f"{self.v('deadline.send_date')}. The fastest is {self.v(f'{best}.name')}, arriving on "
                f"{self.v(f'{best}.arrives_on')}: true cost {self.v(f'{best}.cost_pct')} of the "
                f"amount, {self.v(f'{best}.total_cost')} in total, and you would pay "
                f"{self.v(f'{best}.parent_pays')}. Ask the university whether it can wait."
            )
        if self.facts.value("deadline.cheapest_misses") == "yes":
            cheapest = ranked[0]
            return (
                f"The lowest true cost overall is {self.v(f'{cheapest}.name')} at "
                f"{self.v(f'{cheapest}.cost_pct')}, but it would arrive on "
                f"{self.v(f'{cheapest}.arrives_on')}, after your due date. The cheapest provider that "
                f"arrives in time is {cost} It arrives on {self.v(f'{best}.arrives_on')}."
            )
        return (
            f"The lowest true cost is {cost} It arrives on {self.v(f'{best}.arrives_on')}, in time."
        )

    def _has_shortfall(self, pid: str) -> bool:
        return any(n != 0 for n in numbers_in(self.facts.value(f"{pid}.shortfall")))

    def _shortfall_note(self, pids: list[str]) -> str:
        notes = [
            f"{self.v(f'{p}.name')} uses {self.v(f'{p}.charge_code')} charges, so the university may receive {self.v(f'{p}.shortfall')} less than the invoice."
            for p in pids
            if self._has_shortfall(p)
        ]
        return " ".join(notes + (["OUR avoids that for tuition."] if notes else []))

    def _finish(self, text: str) -> Answer:
        if self.legal:
            text = f"I cannot say whether something is legal or within a limit. {INDICATIVE} {text}"
        return Answer(text, list(self.used))

    # --- intents ------------------------------------------------------------------------
    def answer(self, intent: Intent) -> Answer:
        if self.conversation and self.conversation.guide:
            return self._finish(GUIDES[self.conversation.guide])
        handler = {
            Intent.COMPARE: self.compare, Intent.CHARGES: self.charges,
            Intent.DEADLINE: self.deadline, Intent.CHECKLIST: self.checklist,
            Intent.LIMITS: self.limits, Intent.KYC: self.kyc, Intent.STATUS: self.status,
            Intent.DRAFT: self.draft, Intent.REQUEST_APPROVAL: self.request_approval,
            Intent.PLAN: self.plan, Intent.CADENCE: self.cadence, Intent.STRESS: self.stress,
            Intent.COSTS: self.costs, Intent.ARRIVAL: self.arrival,
        }.get(intent, self.help)  # fmt: skip
        return handler()

    # --- student questions: the cost of a city, and the first weeks abroad -----------------
    def _cost_rows(self, count: int) -> str:
        return ", ".join(
            f"{self.v(f'cost.c{i}.city')} {self.v(f'cost.c{i}.total')} "
            f"({self.v(f'cost.c{i}.total_bdt')})"
            for i in range(count)
        )

    def _city_cost(self) -> str:
        parts = ", ".join(f"{word} {self.v(f'cost.line.{key}')}" for key, word in COST_WORDS)
        text = (
            f"{self.v('cost.city')}, {self.v('cost.country_name')}, "
            f"{self.v('cost.housing').lower()}: {parts}. That is {self.v('cost.total')} in all, "
            f"about {self.v('cost.total_bdt')} at the synthetic rate of {self.v('cost.rate')} BDT "
            f"per {self.v('cost.currency')}; the rent alone is {self.v('cost.rent_bdt')} "
            f"({self.v('cost.rent_share')} of the month). With {self.v('cost.other_housing').lower()} "
            f"instead, a month is {self.v('cost.other_total')} ({self.v('cost.other_total_bdt')})."
        )
        if self.facts.has("cost.fits"):
            city, budget = self.v("cost.city"), self.v("cost.budget")
            if self.v("cost.fits") == "yes":
                text += (
                    f" Against your monthly budget of {budget}, {city} fits, with "
                    f"{self.v('cost.spare')} to spare."
                )
            else:
                text += (
                    f" Against your monthly budget of {budget}, {city} does not fit: it is "
                    f"{self.v('cost.gap')} short."
                )
        return text

    def _cost_list(self) -> str:
        listed = int(self.v("cost.listed"))
        housing = self.v("cost.housing").lower()
        scope = self.v("cost.country_name") if self.facts.has("cost.country_name") else ""
        place = f"Student costs in {scope}" if scope else "Student costs across the cities I know"
        if not self.facts.has("cost.budget"):
            return (
                f"{place}, from the cheapest month ({housing}): {self._cost_rows(listed)}. Name a "
                "city for the full month, or give me a monthly budget in taka and I will say "
                "which cities fit."
            )
        fitting, count = self.v("cost.fitting"), self.v("cost.count")
        text = (
            f"With a monthly budget of {self.v('cost.budget')}, {fitting} of {count} cities fit "
            f"({housing})."
        )
        if fitting == "0":
            return (
                f"{text} No city fits. The cheapest is {self.v('cost.c0.city')} at "
                f"{self.v('cost.c0.total_bdt')}, {self.v('cost.c0.gap')} short."
            )
        text += f" Cheapest first: {self._cost_rows(listed)}."
        if int(fitting) > listed:
            text += f" These are the {listed} cheapest."
        return text

    def costs(self) -> Answer:
        if self.facts.has("cost.no_figures"):
            return self._finish(
                f"I do not have student cost figures for {self.v('cost.no_figures')}. I have them "
                f"for {self.v('cost.countries')}. {INDICATIVE}"
            )
        body = self._city_cost() if self.facts.has("cost.city") else self._cost_list()
        return self._finish(" ".join(f"{body} {self.v('cost.disclaimer')}".split()))

    def arrival(self) -> Answer:
        where = self.v("arrival.country")
        steps = " ".join(f"{label}: {self.v(f'arrival.{key}')}." for key, label in ARRIVAL_STAGES)
        if self.v("arrival.general") == "yes":
            opening = (
                "A general list for any country, because steps specific to yours are not loaded."
            )
            closing = (
                "Tell me the country, for example 'What should I do when I arrive in Germany?', "
                "and I will give the steps specific to it."
            )
        else:
            opening = (
                f"Arrival guide for {where} (indicative: rules for visas, work and registration "
                "change, so confirm them with your university and the official government page)."
            )
            closing = ""
        text = (
            f"{opening} {steps} That is {self.v('arrival.count')} steps; open Student guide, then "
            f"Arrival checklist, for the hint on each and to tick them off. {closing} {INDICATIVE}"
        )
        return self._finish(" ".join(text.split()))

    def stress(self) -> Answer:
        if not self._have_quote() or not self.facts.has("stress.count"):
            return self._finish(NO_QUOTE)
        cases = [
            f"if each {self.v('stress.currency')} costs {self.v(f'stress.{i}.drop')} more taka, you pay "
            f"{self.v(f'stress.{i}.pays')}, which is {self.v(f'stress.{i}.extra')} more "
            f"({self.v(f'stress.{i}.extra_pct')})"
            for i in range(int(self.v("stress.count")))
        ]
        joined = "; ".join(cases)
        text = (
            f"Currency-drop stress test for {self.v('quote.target')} with {self.v('stress.provider')}. "
            f"Today you would pay {self.v('stress.baseline_pays')}. "
            + joined[0].upper()
            + joined[1:]
            + f". {self.v('stress.assumption')} This is a what-if on synthetic rates, not a "
            f"forecast. {INDICATIVE}"
        )
        return self._finish(" ".join(text.split()))

    def help(self) -> Answer:
        return self._finish(
            "I can explain provider costs and the hidden FX margin, the charge codes OUR, SHA and BEN, "
            "your deadline, the documents a bank may ask for, KYC and the sandbox limits. "
            "I can also tell you the rent and the cost of a month in a student city, which city "
            "fits a budget in taka, and what to do before you fly and in your first weeks abroad. "
            "I only use numbers from the engine, and I cannot approve, submit, cancel or change anything. "
            "A human must do that in the app."
        )

    def compare(self) -> Answer:
        if not self._have_quote():
            return self._finish(NO_QUOTE)
        ranked = self._ranked()
        named = [p for p in mentioned_providers(self.message, self.provider_ids) if p in ranked]
        if len(named) >= 2:
            return self._compare_pair(named, ranked)
        if len(named) == 1:
            return self._provider_detail(named[0])
        parts = [
            f"{self.v(f'{p}.name')} {self.v(f'{p}.cost_pct')} ({self.v(f'{p}.total_cost')})"
            for p in ranked
        ]
        text = "Ranked by true total cost, cheapest first: " + "; ".join(parts) + ". "
        text += "The ranking includes the hidden FX margin and every fee. "
        text += self._shortfall_note(ranked) + " " + SANDBOX_NOTE
        return self._finish(" ".join(text.split()))

    def _compare_pair(self, named: list[str], ranked: list[str]) -> Answer:
        cheap, dear = sorted(named[:2], key=ranked.index)
        prefix = ""
        if named[0] != cheap:
            prefix = f"Actually, {self.v(f'{cheap}.name')} is the cheaper one. "
        n_cheap, n_dear = self.v(f"{cheap}.name"), self.v(f"{dear}.name")
        text = (
            f"{prefix}{n_cheap} is cheaper than {n_dear}. Its true total cost is "
            f"{self.v(f'{cheap}.cost_pct')} of the amount, against {self.v(f'{dear}.cost_pct')}, "
            f"a gap of {self.v(f'diff.{cheap}.{dear}.cost_pct')}. "
            f"The main driver is the hidden FX margin: {n_cheap} adds {self.v(f'{cheap}.margin_pct')} "
            f"over the mid-market rate and {n_dear} adds {self.v(f'{dear}.margin_pct')}. "
            f"In BDT the totals are {self.v(f'{cheap}.total_cost')} and {self.v(f'{dear}.total_cost')}, "
            f"so the cheaper provider saves {self.v(f'diff.{cheap}.{dear}.total_cost')}. "
            f"Fixed plus SWIFT fees are {self.v(f'{cheap}.fixed_fee')} plus {self.v(f'{cheap}.swift_fee')} "
            f"for {n_cheap} and {self.v(f'{dear}.fixed_fee')} plus {self.v(f'{dear}.swift_fee')} for {n_dear}. "
            f"{self._shortfall_note([cheap, dear])} {SANDBOX_NOTE}"
        )
        return self._finish(" ".join(text.split()))

    def _provider_detail(self, pid: str) -> Answer:
        name = self.v(f"{pid}.name")
        text = (
            f"{name}: rank by true total cost is {self.v(f'{pid}.rank')}. The hidden FX margin is "
            f"{self.v(f'{pid}.margin_pct')}, which costs {self.v(f'{pid}.fx_cost')}. Fixed fee "
            f"{self.v(f'{pid}.fixed_fee')}, SWIFT fee {self.v(f'{pid}.swift_fee')}, intermediary fee "
            f"{self.v(f'{pid}.intermediary_fee')}, receiving fee {self.v(f'{pid}.receiving_fee')}. "
            f"Total cost {self.v(f'{pid}.total_cost')}, which is {self.v(f'{pid}.cost_pct')} of the amount. "
            f"The parent pays {self.v(f'{pid}.parent_pays')} and the university receives "
            f"{self.v(f'{pid}.receives')}. Charge code {self.v(f'{pid}.charge_code')}. "
            f"{self._shortfall_note([pid])} {SANDBOX_NOTE}"
        )
        return self._finish(" ".join(text.split()))

    def charges(self) -> Answer:
        text = (
            "OUR means the sender pays all charges, so the university should receive the full amount. "
            "SHA shares them: you pay your bank and the university bears the receiving and intermediary "
            "charges. BEN makes the beneficiary pay everything, which carries the highest risk of a short "
            "payment. For tuition I recommend OUR, because a short payment can mean a late fee or an "
            "invoice that cannot be matched. Check the university's own payment instructions."
        )
        if self._have_quote():
            text += " " + self._shortfall_note(self._ranked())
        return self._finish(" ".join(text.split()))

    def deadline(self) -> Answer:
        if not self.facts.has("plan.latest"):
            return self._finish(
                "I do not have a due date yet. Enter the university's due date on the Dashboard "
                "or in the quote form and I will work backwards from it."
            )
        text = (
            f"To reach the university by {self.v('plan.due_date')}, send by {self.v('plan.latest')} "
            f"at the latest. I suggest {self.v('plan.recommended')}. The plan skips weekends and public "
            f"holidays in Bangladesh and {self.v('plan.country')}, assumes {self.v('plan.settlement_days')} "
            f"business days to settle plus {self.v('plan.buffer_days')} days of buffer, and a bank cut-off at "
            f"{self.v('plan.cutoff')} Dhaka time. Status: {self.v('plan.status')}. {INDICATIVE}"
        )
        return self._finish(" ".join(text.split()))

    def checklist(self) -> Answer:
        items = [k for k in self.facts.keys_with_prefix("checklist.") if k != "checklist.title"]
        if not items:
            return self._finish(
                "I do not have a checklist for that yet. Pick a country on the Documents screen."
            )
        listing = ", ".join(self.v(k) for k in items)
        return self._finish(
            f"For {self.v('checklist.title')} the bank may ask for: {listing}. {INDICATIVE}"
        )

    def limits(self) -> Answer:
        text = (
            f"The sandbox applies its own caps: {self.v('limit.per_transaction')} per transaction and "
            f"{self.v('limit.daily')} per day. These are our choices for the demo, not legal limits. "
            f"The only Bangladesh figure I hold is {self.v('bd.living_expense')} a month for living costs, "
            f"with {self.v('bd.living_uplift')} more for high-cost places. It comes from a secondary source "
            f"and is NOT verified. {INDICATIVE}"
        )
        return self._finish(" ".join(text.split()))

    def kyc(self) -> Answer:
        if not self.facts.has("kyc.status"):
            return self._finish("I cannot see a KYC status for this account.")
        return self._finish(
            f"Your mock KYC status is {self.v('kyc.status')}. {self.v('kyc.message')} "
            "This is simulated: no real identity data is used."
        )

    def status(self) -> Answer:
        if not self.facts.has("payment.state"):
            return self._finish(
                "Open a payment on the Tracker screen and ask again, so I know which one you mean."
            )
        text = f"The payment to deliver {self.v('payment.target')} is {self.v('payment.state')}."
        if self.facts.has("payment.uetr"):
            text += f" Its tracking reference (UETR) is {self.v('payment.uetr')}."
        # The bank check has its own paragraph below, so its blocker is not said twice.
        blockers = [
            k for k in self.facts.keys_with_prefix("blocker.") if k != "blocker.BANK_REVIEW_PENDING"
        ]
        if blockers:
            text += " What blocks it now: " + " ".join(self.v(k) for k in blockers)
        text += self._bank_check()
        return self._finish(text + " Everything here is simulated.")

    def _bank_check(self) -> str:
        """What the bank's check means for the parent, only from the review's own facts."""
        if not self.facts.has("review.headline"):
            return ""
        text = f" Bank check: {self.v('review.headline')}. {self.v('review.plain')}"
        if self.facts.has("review.score"):
            text += f" The AI's risk score is {self.v('review.score')}. {self.v('review.warning')}"
            if re.search(r"why|factor|reason|made of|explain|score", self.message, re.I):
                text += " The score is made of four things: " + " ".join(
                    self.v(k) for k in self.facts.keys_with_prefix("review.factor.")
                )
            text += (
                " Every payment still needs your own authorization with MFA, whatever the score."
            )
        if self.facts.has("review.clock"):
            text += f" It has {self.v('review.clock')}."
        for key in self.facts.keys_with_prefix("review.signal."):
            text += f" {self.v(key)}"
        if self.facts.has("review.asked"):
            text += f" The bank asked: {self.v('review.asked')}"
        if self.facts.has("review.reason"):
            text += f" {self.v('review.reason')}"
        if re.search(r"prepar|bring|need|documents?|ask", self.message, re.I):
            for key in self.facts.keys_with_prefix("review.prepare."):
                text += f" To prepare: {self.v(key)}."
        return text

    def draft(self) -> Answer:
        if not self._have_quote():
            return self._finish(NO_QUOTE)
        ranked = self._ranked()
        named = [p for p in mentioned_providers(self.message, self.provider_ids) if p in ranked]
        pid = named[0] if named else ranked[0]
        proposal = {
            "tool": "create_draft",
            "args": {"quote_id": self.quote_id, "provider_id": pid},
            "requires_human": True,
            "missing": ["recipient_id", "reference"],
        }
        text = (
            f"I can propose a draft with {self.v(f'{pid}.name')}, total cost {self.v(f'{pid}.total_cost')}. "
            "I only propose it: you confirm the draft in the app and add the recipient and the reference. "
            "Approval is a separate step that only you can do, with a fresh MFA code."
        )
        answer = self._finish(" ".join(text.split()))
        answer.proposals.append(proposal)
        return answer

    def request_approval(self) -> Answer:
        if not self.payment_id:
            return self._finish("Open the payment first, then ask me to request approval.")
        proposal = {
            "tool": "request_approval",
            "args": {"payment_id": self.payment_id},
            "requires_human": True,
            "missing": [],
        }
        text = (
            "I can propose requesting approval. It moves the payment to pending approval, where the "
            "guards run: verified KYC, an allowlisted recipient, the sandbox caps and a valid quote. "
            "You decide whether to send it, and only you can approve it afterwards."
        )
        answer = self._finish(text)
        answer.proposals.append(proposal)
        return answer

    # --- tasks ----------------------------------------------------------------------------
    def _task_gap(self, example_key: str, what_to_plan: str) -> Answer | None:
        """The answer when a task could not run: say why and give an example."""
        if self.facts.has("task.error"):
            return self._finish(
                f"I could not build that plan: {self.v('task.error')}. "
                f"You can try again, for example: {self.v(example_key)}."
            )
        if self.facts.has("task.confirm"):
            return self._finish(
                f"Before I plan {what_to_plan}, please check what I understood: "
                f"{self.v('task.confirm')}. Say yes to go ahead, or tell me what to change."
            )
        if self.facts.has("task.missing"):
            note = f" {self.v('task.conflict')}." if self.facts.has("task.conflict") else ""
            return self._finish(
                f"To plan {what_to_plan} I still need {self.v('task.missing')}.{note} "
                f"For example: {self.v(example_key)}."
            )
        return None

    def plan(self) -> Answer:
        if (gap := self._task_gap("example.plan", "your payment")) is not None:
            return gap
        if not self._have_quote():
            return self._finish(NO_QUOTE)
        ranked = self._ranked()
        best = self._deadline_pick(ranked)
        parts = [
            f"I made a quote for {self.v('quote.target')} to {self.v('request.country')} and "
            "prepared your payment plan.",
            self._lowest_cost_sentence(ranked, best),
            self._shortfall_note(ranked),
        ]
        if self.facts.has("plan.latest"):
            parts.append(
                f"To reach the university by {self.v('plan.due_date')}, send by "
                f"{self.v('plan.latest')} at the latest; I suggest {self.v('plan.recommended')}. "
                f"Deadline status: {self.v('plan.status')}."
            )
        else:
            parts.append("Tell me the university's due date and I will plan the deadline too.")
        parts.append(f"Your mock KYC status is {self.v('kyc.status')}.")
        saved = int(self.v("recipient.matching") or 0)
        allowlisted = int(self.v("recipient.allowlisted") or 0)
        if saved == 0:
            parts.append(
                "You have no recipient saved for this country yet: add the university first."
            )
        elif allowlisted == 0:
            parts.append("Your saved recipient still has to be allowlisted with a fresh MFA code.")
        else:
            parts.append("You already have an allowlisted recipient.")
        parts.append(
            f"Documents: {self.v('docs.provided')} of {self.v('docs.total')} on the checklist are ready."
        )
        parts.append(
            "Review the plan below. I can only propose the draft: you confirm it and add the "
            "payment reference, and only you can approve it, with a fresh MFA code. " + INDICATIVE
        )
        args = {"quote_id": self.quote_id, "provider_id": best}
        missing = ["reference", "recipient_id"]
        if self.task is not None:
            missing = list(self.task.missing)
            if self.task.recipient_id:
                args["recipient_id"] = self.task.recipient_id
        answer = self._finish(" ".join(" ".join(parts).split()))
        answer.proposals.append(
            {"tool": "create_draft", "args": args, "requires_human": True, "missing": missing}
        )
        return answer

    def cadence(self) -> Answer:
        if (gap := self._task_gap("example.cadence", "how often to send")) is not None:
            return gap
        order = [
            k for k in ("monthly", "quarterly", "termly", "upfront")
            if self.facts.has(f"cadence.{k}.name")
        ]  # fmt: skip
        if not order:
            return self._finish(
                "Tell me how much you send and for how many months, and I will compare the ways of "
                f"sending it. For example: {EXAMPLE_CADENCE_HINT}"
            )

        def line(k: str) -> str:
            count = self.facts.value(f"cadence.{k}.transfers")
            unit = "transfer" if count == "1" else "transfers"
            return (
                f"{self.v(f'cadence.{k}.name')}: {self.v(f'cadence.{k}.transfers')} {unit} of "
                f"{self.v(f'cadence.{k}.per_transfer')} with {self.v(f'cadence.{k}.provider')}, "
                f"{self.v(f'cadence.{k}.total_cost')} in total"
            )

        cheapest_name = self.v("cadence.cheapest")
        cheapest = next(k for k in order if self.facts.value(f"cadence.{k}.name") == cheapest_name)
        text = (
            f"To send {self.v('cadence.total')} over {self.v('cadence.months')} months, this is the "
            f"true total cost of each way of sending it. {'; '.join(line(k) for k in order)}. "
        )
        if cheapest != "monthly":
            text += (
                f"The cheapest on paper is {cheapest_name}, which saves "
                f"{self.v(f'cadence.{cheapest}.saving')} compared with sending every month. "
            )
        text += (
            "Fixed and SWIFT fees are paid on every transfer, so fewer transfers cost less. But "
            "sending less often moves money before it is needed, and StudyRoute does not predict "
            "exchange rates, so the cheapest option is not automatically the best one. "
            + INDICATIVE
        )
        return self._finish(" ".join(text.split()))
