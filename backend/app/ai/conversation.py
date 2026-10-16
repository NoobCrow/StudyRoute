"""Read-only conversation routing layered over the financial intent reader.

The small trained reader is not a generative chat model. Greetings, app guidance and
pronoun follow-ups need their own routes instead of falling into the same HELP text.
History is an untrusted, bounded topic hint only: never a source of values, record IDs,
permissions, task confirmations or actions. Payment task continuation stays in NLU.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass

from app.ai.intents import Intent
from app.ai.policy import check_text


@dataclass(frozen=True)
class Route:
    topic: str
    intent: Intent = Intent.HELP
    guide: str | None = None
    follow_up: bool = False


# Reviewed, number-free guidance. Actual amounts, dates, KYC status and comparisons
# still come from Responder and the engine's facts, not this catalogue.
GUIDES: dict[str, str] = {
    "greeting": (
        "Hello! I'm the StudyRoute assistant. Are you planning tuition or living costs abroad, "
        "comparing providers, or trying to complete your mock identity check? Tell me what you "
        "need help with. This sandbox does not move real money."
    ),
    "greeting_bn": (
        "হ্যালো! আমি StudyRoute assistant। বিদেশে tuition বা living costs পাঠানোর পরিকল্পনা, "
        "provider তুলনা, documents এবং mock KYC নিয়ে সাহায্য করতে পারি। কোনটি জানতে চান? "
        "এটি sandbox—এখানে আসল টাকা পাঠানো হয় না।"
    ),
    "about": (
        "StudyRoute is a sandbox for families planning education payments abroad from "
        "Bangladesh. "
        "It compares providers' true costs, checks arrival deadlines, explains document "
        "requirements "
        "and tracks simulated payments. Start with Compare providers, enter the amount "
        "the university "
        "must receive and its due date, then review the quotes. All rates and transfers "
        "are synthetic; "
        "a human reviews and approves in the app."
    ),
    "about_bn": (
        "StudyRoute হলো বাংলাদেশ থেকে বিদেশে পড়াশোনার খরচ পাঠানোর পরিকল্পনার একটি sandbox app। "
        "এখানে provider-এর মোট খরচ তুলনা, deadline, documents ও simulated payment "
        "tracking দেখা যায়। "
        "Compare providers-এ প্রয়োজনীয় amount ও due date দিয়ে শুরু করুন। Rates ও "
        "transfers synthetic; "
        "এখানে আসল টাকা পাঠানো হয় না।"
    ),
    "thanks": (
        "You're welcome! If you want to continue, ask about your quote, "
        "deadline or document checklist."
    ),
    "identity": (
        "I'm StudyRoute's read-only finance assistant, not a bank or a payment approver. "
        "In offline mode I use topic routing, reviewed guidance and engine facts, not an "
        "external "
        "generative language model. The trained reader extracts payment details; it does "
        "not write "
        "free-form answers. An externally configured language model can explain the same "
        "checked facts."
    ),
    "start": (
        "Start on the Dashboard and complete the mock identity check. Add the university "
        "in Recipients, "
        "then open Compare and enter the amount it must receive, destination and due "
        "date. Review total "
        "cost, shortfall risk and arrival time before creating a draft. A human must "
        "review and approve "
        "with MFA. Use mock documents only; no real identity data or money is needed."
    ),
    "kyc_explain": (
        "KYC means Know Your Customer: an identity and source-of-funds check. In "
        "StudyRoute it is "
        "simulated, not real bank verification. An incomplete mock check blocks approval,"
        " but you can "
        "still explore quotes. To see your own result, ask 'What is my KYC status?'"
    ),
    "kyc_steps": (
        "On the Dashboard, open Identity check and choose Submit mock documents. Follow the mock "
        "document prompts, then check that the simulated status changes to verified. Do "
        "not upload "
        "real passports or national IDs. If the status is still blocked, read the "
        "missing-document "
        "message before trying to approve. Completing KYC does not itself approve or send"
        " a payment."
    ),
    "charges_explain": (
        "OUR means the sender pays the transfer charges. SHA shares charges, so "
        "deductions can reduce "
        "what the recipient receives. BEN charges the beneficiary, also risking a "
        "shortfall. For an "
        "exact tuition invoice, review the OUR quote and the shortfall column, then "
        "confirm the actual "
        "bank's terms. These sandbox providers and fees are synthetic."
    ),
    "cost_explain": (
        "The advertised fee is not the whole cost. A provider can also add an "
        "exchange-rate margin "
        "and intermediary charges. Compare shows the parent's total outlay, hidden "
        "margin, recipient "
        "shortfall risk and arrival time together. Run a quote for an actual comparison; "
        "I cannot "
        "name the cheapest provider or invent a live rate without engine results."
    ),
    "deadline_explain": (
        "The deadline planner works backwards from the university's due date, using "
        "settlement time, "
        "a safety buffer, non-working days and the Dhaka cut-off. The recommended send date is a "
        "planning hint, not a delivery guarantee. Enter a due date on the Dashboard or in"
        " Compare "
        "to get calculated dates, then confirm timing with your AD bank."
    ),
    "documents_steps": (
        "Use Documents for the destination and payment purpose shown in your quote. Review the "
        "checklist and add mock evidence where the app requests it; do not upload real personal "
        "documents for this demo. Bank requirements can differ. Ask for the checklist for your "
        "destination and confirm the real requirements with your AD bank."
    ),
    "status_steps": (
        "Open Payments and select the payment you mean. Its tracker shows the current simulated "
        "state and any blockers. Keep that payment open when asking me about its status. "
        "I cannot "
        "infer a payment's state from a previous message or submit it on your behalf."
    ),
    "escrow": (
        "Smart escrow is StudyRoute's simulated on-chain payment demonstration. Review "
        "the contract "
        "state and available steps on Smart escrow; it is not a real bank transfer or a "
        "production "
        "custody service. I can explain the feature, but I cannot release funds or sign "
        "transactions."
    ),
    "bank_network": (
        "Bank network demonstrates a simulated bank-transfer network. Its records are demo data, "
        "not proof of a live banking connection. Use the Bank network screen to inspect "
        "the demo; "
        "use Payments to inspect a particular payment's tracker."
    ),
    "audit": (
        "Audit log records important app decisions and actions so you can inspect what happened, "
        "including assistant replies and blocked requests. Open Audit log to review "
        "entries available "
        "to your account. I cannot edit the audit history or grant access to another "
        "household's data."
    ),
    "clarify": (
        "I'm not sure which part you mean. Are you asking about StudyRoute itself, "
        "provider costs, "
        "a payment deadline, documents, or your mock KYC? Name the screen or describe the"
        " problem "
        "and I will focus on that."
    ),
    "out_of_scope": (
        "That is outside StudyRoute's education-payment scope. I can help with provider "
        "comparisons, "
        "deadlines, documents and simulated payment tracking, but I cannot reliably answer that "
        "general question in offline mode. What would you like to check in StudyRoute?"
    ),
}


def _normal(text: str) -> str:
    return " ".join(text.casefold().strip().split()).strip(" .!?।")


def _explicit(text: str) -> Route | None:
    t = _normal(text)
    if re.fullmatch(
        r"(?:hi|hello|hey|assalamu ?alaikum|salam|হাই|হ্যালো|আসসালামু আলাইকুম)"
        r"(?: there| studyroute)?",
        t,
    ):
        bn = bool(re.search(r"[\u0980-\u09ff]", t))
        return Route("greeting", guide="greeting_bn" if bn else "greeting")
    if re.fullmatch(r"(?:thanks|thank you|thank you so much|ধন্যবাদ|dhonnobad|ok thanks)", t):
        return Route("thanks", guide="thanks")
    if re.search(
        r"who are you|are you (?:an? )?(?:ai|bot)|template mode|offline mode|"
        r"same answer|api key|তুমি কে",
        t,
    ):
        return Route("identity", guide="identity")
    if re.fullmatch(
        r"(?:what is (?:it|this|that)|what'?s (?:it|this|that)|what does (?:it|this|that) mean)", t
    ):
        return None  # Resolve a referent before choosing the app overview.
    if re.search(
        r"what is studyroute|what does (?:this app|studyroute) do|about studyroute|"
        r"what is this app|এটা কি|এটা কী|ata ki|eta ki",
        t,
    ):
        bn = bool(re.search(r"[\u0980-\u09ff]|(?:ata|eta) ki", t))
        return Route("about", guide="about_bn" if bn else "about")
    if re.search(
        r"how (?:do i|to|can i) (?:start|use (?:this|the app|studyroute))|"
        r"getting started|কিভাবে শুরু|kivabe (?:use|shuru)",
        t,
    ):
        return Route("start", guide="start")
    if re.search(r"\bkyc\b|identity check|পরিচয় যাচাই|পরিচয় যাচাই", t):
        if re.search(r"how|fix|complete|submit|করব|kivabe", t):
            return Route("kyc", Intent.KYC, "kyc_steps")
        if re.search(r"what (?:is|does)|mean|explain|\bki\b|কী|কি", t) and not re.search(
            r"\bmy\b|status|blocked|missing", t
        ):
            return Route("kyc", Intent.KYC, "kyc_explain")
        return Route("kyc", Intent.KYC)
    if re.search(r"smart escrow|\bescrow\b", t):
        return Route("escrow", guide="escrow")
    if "bank network" in t:
        return Route("bank_network", guide="bank_network")
    if "audit log" in t:
        return Route("audit", guide="audit")
    # Narrow read-only routes: never create a quote, draft or approval from history.
    if re.search(r"\b(?:our|sha|ben)\b|charge codes?|shortfall", t):
        return Route("charges", Intent.CHARGES)
    if re.search(r"deadline|due date|when should i send|latest send", t):
        return Route("deadline", Intent.DEADLINE)
    if re.search(r"documents?|checklist|paperwork", t):
        return Route("documents", Intent.CHECKLIST)
    if re.search(r"daily limit|transaction limit|sandbox limits?|legal limit", t):
        return Route("limits", Intent.LIMITS)
    if re.search(r"payment status|track (?:my|the|a) payment|where is my payment", t):
        return Route("status", Intent.STATUS)
    if re.search(
        r"hidden (?:fx )?margin|exchange.rate margin|what (?:is|are).{0,25}(?:fees?|cost)|"
        r"how.{0,20}(?:fees?|cost).{0,15}work",
        t,
    ):
        return Route("cost", Intent.COMPARE, "cost_explain")
    if re.search(r"provider|quote|compare|cheapest|exchange rate", t):
        return Route("cost", Intent.COMPARE)
    return None


_FOLLOWUP = re.compile(
    r"what is (?:it|this|that)|what'?s (?:it|this|that)|what does (?:it|this|that) mean|"
    r"(?:please )?(?:explain|tell me more|explain more|why|how do i fix (?:it|this|that)|"
    r"how do i do (?:it|this|that)|what should i do|what next|আরও বলো|bujhi nai)"
)
_MORE = {
    "kyc": "kyc_explain",
    "charges": "charges_explain",
    "cost": "cost_explain",
    "deadline": "deadline_explain",
    "documents": "documents_steps",
    "status": "status_steps",
}


def route_message(message: str, history: Sequence[str] = ()) -> Route | None:
    """A route can only request a read-only handler or reviewed prose, never an action."""
    explicit = _explicit(message)
    if explicit:
        return explicit
    t = _normal(message)
    if not _FOLLOWUP.fullmatch(t):
        return None
    # Follow a chain of short clarifications, but stop at any unrelated, blocked
    # or unknown turn. History never supplies amounts or task confirmations.
    prior = None
    for previous in reversed(history[-6:]):
        if check_text(previous).blocked:
            break
        prior = _explicit(previous)
        if prior or not _FOLLOWUP.fullmatch(_normal(previous)):
            break
    if prior and prior.topic not in {"greeting", "thanks"}:
        guide = _MORE.get(prior.topic, prior.guide)
        if prior.topic == "kyc" and re.search(r"fix|do|next", t):
            guide = "kyc_steps"
        return Route(prior.topic, prior.intent, guide, True)
    if re.fullmatch(
        r"what is (?:it|this|that)|what'?s (?:it|this|that)|what does (?:it|this|that) mean", t
    ):
        return Route("about", guide="about")
    return Route("clarify", guide="clarify")
