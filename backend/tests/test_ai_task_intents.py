"""When the assistant starts a task (plan a payment, plan a send schedule) and when it must not."""

from __future__ import annotations

from datetime import date

import pytest

from app.ai.intents import Intent, choose_intent
from app.ai.request_parser import parse_request

TODAY = date(2026, 10, 14)
CURRENCIES = {"GBP", "USD", "EUR", "AUD", "CAD", "MYR"}


def choose(message: str, *, context: bool = False) -> Intent:
    return choose_intent(message, parse_request(message, CURRENCIES, TODAY), has_context=context)


@pytest.mark.parametrize(
    "message",
    [
        "I need to pay GBP 10,000 tuition by 28 October",
        "Help me pay GBP 5,000",
        "How much will it cost to send GBP 10,000?",
        "Plan GBP 10,000 tuition due 28 October",
        "Please get me a quote for 8,000 euros",
        "I want to send 25,000 USD for fees",
    ],
)
def test_a_payment_request_with_an_amount_starts_a_plan(message: str) -> None:
    assert choose(message) is Intent.PLAN


@pytest.mark.parametrize(
    "message",
    [
        "How often should I send GBP 800 a month for 9 months?",
        "Is monthly or quarterly cheaper for GBP 1,000 a month?",
        "What is the cheapest way to send 1,200 pounds a month?",
        "Should I send GBP 12,000 all at once or in instalments?",
    ],
)
def test_a_question_about_how_often_to_send_starts_a_send_plan(message: str) -> None:
    assert choose(message) is Intent.CADENCE


@pytest.mark.parametrize(
    ("message", "expected"),
    [
        ("What is the limit for GBP 50,000?", Intent.LIMITS),
        ("Is it legal to send GBP 10,000?", Intent.HELP),
        ("Why is Provider B cheaper than A?", Intent.COMPARE),
        ("What is the deadline plan?", Intent.DEADLINE),
        ("when should I send?", Intent.DEADLINE),
    ],
)
def test_questions_that_only_mention_money_never_create_a_quote(
    message: str, expected: Intent
) -> None:
    assert choose(message) is expected


def test_an_amount_inside_an_open_quote_is_a_question_about_that_quote() -> None:
    assert choose("Why is B cheaper for GBP 10,000?", context=True) is Intent.COMPARE
    assert choose("Plan GBP 10,000 tuition due 28 October", context=True) is Intent.PLAN


def test_a_clear_intent_to_pay_without_an_amount_still_starts_a_plan_that_asks() -> None:
    assert choose("I need to pay tuition") is Intent.PLAN
    assert choose("Help me pay my fees") is Intent.PLAN
    assert choose("plan my payment") is Intent.PLAN
