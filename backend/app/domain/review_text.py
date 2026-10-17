"""Plain words for parents and short checks for the reviewer, one entry for each review signal.

Written for a parent who has never dealt with an AD bank. Nothing here accuses anyone: a signal is a
reason the bank looks closer, and the usual reason is simply a large or unfamiliar payment. These
texts are fixed so they can be checked; the assistant only repeats them and the engine's figures.
"""

from __future__ import annotations

from typing import Any

# The four things the AI's risk score is made of, in plain words, for each way it can lean.
FACTOR_TEXT: dict[str, dict[str, str]] = {
    "AMOUNT": {
        "title": "Amount",
        "raises": "The amount is larger than most similar payments.",
        "neutral": "The amount is typical for similar payments.",
        "lowers": "The amount is smaller than most similar payments.",
    },
    "FREQUENCY": {
        "title": "Frequency",
        "raises": "This household has made several payments recently.",
        "neutral": "The number of recent payments is normal.",
        "lowers": "There have been few recent payments.",
    },
    "TIMELINE": {
        "title": "Timeline",
        "raises": "This payment comes soon after the previous one.",
        "neutral": "The timing is normal.",
        "lowers": "A good while has passed since the last payment.",
    },
    "PERSON": {
        "title": "Person",
        "raises": "You have not paid this person or university before.",
        "neutral": "There is nothing unusual about who is being paid.",
        "lowers": "You have paid this receiver before.",
    },
}

SIGNAL_TEXT: dict[str, dict[str, Any]] = {
    "BANK_AUTHORIZES_ALL": {
        "title": "The bank authorizes every payment",
        "parent_means": "In this setup the bank says yes to every payment, whatever its score.",
        "parent_why": "It is the bank's own rule, not a sign anything is wrong with this payment.",
        "prepare": ["The university's invoice or fee letter showing this amount"],
        "reviewer_check": "Does the payment match the invoice? No risk reason was found.",
    },
    "AI_RISK": {
        "title": "The bank's AI model looks closer",
        "parent_means": (
            "A computer model compared this payment with many practice payments and found it "
            "looks unusual. A person at the bank will now check it."
        ),
        "parent_why": (
            "The model is only a prompt to look closer. It can be wrong, it never decides, "
            "and the person at the bank does."
        ),
        "prepare": [
            "The university's invoice or fee letter showing this amount",
            "A short note of where the money comes from (savings, salary, sale of property)",
        ],
        "reviewer_check": (
            "Does the payment make sense for this family and this invoice? "
            "The model can be wrong; the factors it named are listed above."
        ),
    },
    "LARGE_AMOUNT": {
        "title": "Large payment",
        "parent_means": (
            "Banks look at big payments more closely. This one is above the sandbox line "
            "for a quick check."
        ),
        "parent_why": "It protects your money. It is routine and says nothing against you.",
        "prepare": [
            "The university's invoice or fee letter showing this amount",
            "A short note of where the money comes from (savings, salary, sale of property)",
        ],
        "reviewer_check": "Does the invoice match the amount, and is the source of funds clear?",
    },
    "POSSIBLE_SPLIT": {
        "title": "Several payments close together",
        "parent_means": (
            "There are several payments in a few days that add up to a large amount. "
            "Banks ask about this so that one big payment is not hidden inside small ones."
        ),
        "parent_why": (
            "Paying in instalments is normal for fees, so the bank only wants to hear the reason."
        ),
        "prepare": [
            "The university's instalment plan or fee schedule",
            "A line saying why you are paying in parts",
        ],
        "reviewer_check": "Is there a plausible reason (an instalment plan) for the pattern?",
    },
    "NAME_CHECK": {
        "title": "Name needs a second look",
        "parent_means": "The receiver's name needs a manual check against the bank's list.",
        "parent_why": (
            "A name can look like another name. A person checks it so nobody is stopped by mistake."
        ),
        "prepare": [
            "The receiver's full legal name exactly as on the invoice",
            "The invoice or offer letter",
        ],
        "reviewer_check": (
            "Does the name match the invoice, and is it someone other than a person on any list?"
        ),
    },
    "NEW_RECIPIENT": {
        "title": "First payment to this receiver",
        "parent_means": "You have not paid this receiver before.",
        "parent_why": (
            "A first payment is checked a little more, just to make sure the details are right."
        ),
        "prepare": ["The receiver's account details copied from the university's own invoice"],
        "reviewer_check": "Were the account details taken from an official invoice?",
    },
    "NO_INVOICE": {
        "title": "No invoice on file",
        "parent_means": "No invoice or fee letter has been uploaded for this tuition payment.",
        "parent_why": "The bank wants to see what the money is for.",
        "prepare": ["Upload the university's invoice on the Documents screen"],
        "reviewer_check": "Ask for the invoice before clearing.",
    },
}

STATUS_TEXT: dict[str, dict[str, str]] = {
    "CLEARED_AUTO": {
        "headline": "No bank check needed",
        "parent": "Nothing about this payment needs a person at the bank to look at it first.",
    },
    "OPEN": {
        "headline": "Waiting for the bank",
        "parent": (
            "A person at the bank is checking this payment. You do not need to do anything now."
        ),
    },
    "INFO_REQUESTED": {
        "headline": "The bank has a question",
        "parent": "The bank needs a little more information from you before it can say yes.",
    },
    "CLEARED": {
        "headline": "The bank said yes",
        "parent": "The bank checked this payment and cleared it. You can approve it now.",
    },
    "DECLINED": {
        "headline": "The bank said no",
        "parent": "The bank cannot clear this payment. The reason is shown below.",
    },
}

REASON_TEXT: dict[str, str] = {
    "UNCLEAR_PURPOSE": "The purpose of the payment is not clear yet.",
    "DOCUMENTS_MISSING": "A document the bank needs is missing.",
    "NAME_MISMATCH": "The receiver's name does not match the invoice.",
    "OVER_BANK_POLICY": "It is above what this bank allows for this kind of payment.",
    "OTHER": "See the reviewer's note.",
}

GLOSSARY: list[dict[str, str]] = [
    {
        "term": "AD bank",
        "plain": "A bank that is allowed to handle foreign-currency payments for you.",
    },
    {
        "term": "KYC",
        "plain": "'Know your customer': the bank checks who you are, once, with your documents.",
    },
    {
        "term": "Source of funds",
        "plain": "Where the money you are sending came from, such as salary or savings.",
    },
    {
        "term": "Bank review",
        "plain": "A person at the bank looks at a payment before it goes. Most payments skip this.",
    },
]
