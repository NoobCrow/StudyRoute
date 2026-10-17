"""The assistant answers student questions: the rent in a city, which city fits a budget, and what
to do on arrival.

Both are questions, not tasks: they create nothing, every figure comes from the engine through the
same facts as any other answer, and the number guard checks the reply like any other.
"""

from __future__ import annotations

import gzip
import json
from datetime import date
from pathlib import Path
from typing import Any

import pytest

from app.ai.intents import Intent, choose_intent
from app.ai.nlu.runtime import load_reader
from app.ai.number_guard import numbers_in
from app.ai.request_parser import parse_request
from app.ai.student_topic import StudentTopic, parse_student_topic
from app.domain.rules import Rules, load_rules
from tests.helpers import World

TODAY = date(2026, 10, 14)


def intent_of(message: str, *, has_context: bool = False) -> Intent:
    parsed = parse_request(message, ["GBP", "USD", "EUR"], TODAY)
    return choose_intent(message, parsed, has_context=has_context)


def rules_of(world: World) -> Rules:
    with world.ctx.db.read() as session:
        return load_rules(session)


# --- which questions are student questions ----------------------------------------------------


@pytest.mark.parametrize(
    "message",
    [
        "What is the rent in Manchester?",
        "How much does it cost to live in Germany?",
        "Which city fits a budget of BDT 200,000 a month?",
        "Can I afford London on 2 lakh taka a month?",
        "cost of living in Toronto",
        "Which countries are cheapest for students?",
        "What are the living costs in Australia?",
        "How much is rent in Berlin for a student?",
        "I want to see my student budget",
    ],
)
def test_questions_about_rent_and_the_cost_of_a_city_are_cost_questions(message: str) -> None:
    assert intent_of(message) is Intent.COSTS
    assert intent_of(message, has_context=True) is Intent.COSTS


@pytest.mark.parametrize(
    "message",
    [
        "What should I do when I arrive?",
        "Give me a checklist for my first week abroad",
        "What do I need before I fly to Germany?",
        "How do I settle in?",
        "I need help with my first month in Canada",
        "arrival guide for the UK",
        "How do I open a student bank account there?",
    ],
)
def test_questions_about_arriving_are_arrival_questions(message: str) -> None:
    assert intent_of(message) is Intent.ARRIVAL
    assert intent_of(message, has_context=True) is Intent.ARRIVAL


@pytest.mark.parametrize(
    ("message", "expected"),
    [
        ("I need to pay GBP 800 rent every month", Intent.PLAN),
        ("I need to pay GBP 10,000 tuition before I fly", Intent.PLAN),
        ("Help me pay GBP 5,000 for my first month in London", Intent.PLAN),
        ("When will the money arrive?", Intent.DEADLINE),
        ("Why is Provider B cheaper than A?", Intent.COMPARE),
        ("What is the exchange rate today?", Intent.COMPARE),
        ("What documents do I need?", Intent.CHECKLIST),
        ("What is the living expense limit per month?", Intent.LIMITS),
        ("What if the taka drops 10%?", Intent.STRESS),
    ],
)
def test_payment_requests_and_the_older_questions_keep_their_intent(
    message: str, expected: Intent
) -> None:
    assert intent_of(message) is expected


# --- reading the place and the budget out of the words ---------------------------------------


def test_a_city_names_its_country_too(world: World) -> None:
    topic = parse_student_topic("What is the rent in manchester?", rules_of(world))
    assert (topic.city, topic.country) == ("Manchester", "GB")


def test_a_country_is_read_by_name_and_by_common_short_names(world: World) -> None:
    rules = rules_of(world)
    assert parse_student_topic("living costs in Germany", rules).country == "DE"
    assert parse_student_topic("cost in the UK", rules).country == "GB"
    assert parse_student_topic("studying in the USA", rules).country == "US"
    assert parse_student_topic("studying in Malaysia", rules).city is None


def test_a_word_that_only_contains_a_city_is_not_a_city(world: World) -> None:
    topic = parse_student_topic("rent in Austinville", rules_of(world))
    assert topic.city is None


@pytest.mark.parametrize(
    ("message", "minor"),
    [
        ("a budget of BDT 200,000 a month", 20_000_000),
        ("I have 150000 taka a month", 15_000_000),
        ("2 lakh taka", 20_000_000),
        ("1.5 lakh", 15_000_000),
        ("my budget is Tk 90,000", 9_000_000),
        ("budget of 120000", 12_000_000),
    ],
)
def test_a_monthly_budget_is_read_in_taka(world: World, message: str, minor: int) -> None:
    topic = parse_student_topic(message, rules_of(world))
    assert topic.budget_bdt is not None
    assert (topic.budget_bdt.amount_minor, topic.budget_bdt.currency) == (minor, "BDT")


def test_no_budget_is_invented_from_other_numbers(world: World) -> None:
    rules = rules_of(world)
    assert parse_student_topic("rent in London in 2026", rules).budget_bdt is None
    assert parse_student_topic("What is the rent in Berlin?", rules).budget_bdt is None
    assert parse_student_topic("budget of 3", rules).budget_bdt is None  # too small to be taka


def test_a_studio_is_read_and_a_shared_room_is_the_default(world: World) -> None:
    rules = rules_of(world)
    assert parse_student_topic("rent for my own studio in Leeds", rules).housing == "studio"
    assert parse_student_topic("rent in Berlin", rules).housing == "shared"


def test_a_message_with_no_place_has_no_place(world: World) -> None:
    topic = parse_student_topic("which city is cheapest", rules_of(world))
    assert topic == StudentTopic(None, None, None, "shared")


# --- the answers ------------------------------------------------------------------------------


def ask(world: World, message: str, **context: Any) -> dict[str, Any]:
    response = world.call("POST", "/assistant/chat", json={"message": message, "context": context})
    assert response.status_code == 200, response.text
    return dict(response.json())


def fact_numbers(body: dict[str, Any]) -> set[Any]:
    prompt = body["debug"]["masked_prompt"]
    values = [line.split(" | ", 2)[2] for line in prompt.splitlines() if line.startswith("fact_")]
    return {n for v in values for n in numbers_in(v)}


def test_the_rent_in_a_city_is_the_engines_month_in_local_money_and_taka(world: World) -> None:
    body = ask(world, "What is the rent in Manchester?")
    text = body["reply"]
    assert "Manchester" in text and "United Kingdom" in text
    assert "rent GBP 600.00" in text
    assert "GBP 1,195.00 in all" in text and "BDT 191,200.00" in text
    assert "own studio" in text and "GBP 1,545.00" in text
    assert "160.000000" in text  # the synthetic rate behind the taka figure
    assert "not a survey" in text and "Indicative. Confirm with your AD bank." in text
    assert body["guard"]["status"] == "passed"
    assert set(numbers_in(text)) <= fact_numbers(body)
    assert body["understanding"]["intent"] == "COSTS"
    assert body["proposed_actions"] == [] and body["task"] is None


def test_a_budget_is_set_against_the_city(world: World) -> None:
    fits = ask(world, "Can I afford Manchester on BDT 200,000 a month?")["reply"]
    assert "BDT 200,000.00" in fits and "fits" in fits and "BDT 8,800.00 to spare" in fits
    short = ask(world, "Can I afford London on BDT 200,000 a month?")["reply"]
    assert "does not fit" in short and "BDT 56,800.00" in short


def test_a_country_lists_its_cities_from_the_cheapest(world: World) -> None:
    body = ask(world, "How much does it cost to live in Germany?")
    text = body["reply"]
    assert text.index("Leipzig") < text.index("Berlin") < text.index("Munich")
    assert "EUR 875.00" in text and "BDT 122,500.00" in text
    assert body["guard"]["status"] == "passed"
    assert set(numbers_in(text)) <= fact_numbers(body)


def test_a_budget_alone_names_the_cities_that_fit(world: World) -> None:
    body = ask(world, "Which city fits a budget of BDT 130,000 a month?")
    text = body["reply"]
    assert "BDT 130,000.00" in text and "4 of 20 cities" in text
    assert text.index("Johor Bahru") < text.index("Penang") < text.index("Leipzig")
    assert "BDT 40,820.00" in text and "BDT 122,500.00" in text
    assert "Adelaide" not in text  # BDT 132,800.00 is over the budget
    assert body["guard"]["status"] == "passed"
    assert set(numbers_in(text)) <= fact_numbers(body)


def test_a_budget_too_small_for_any_city_says_how_far_off_it_is(world: World) -> None:
    text = ask(world, "Which city fits a budget of BDT 30,000 a month?")["reply"]
    assert "No city fits" in text
    assert "BDT 10,820.00 short" in text  # Johor Bahru, the cheapest: 40,820 - 30,000


def test_with_no_place_and_no_budget_it_asks_for_one_and_still_helps(world: World) -> None:
    body = ask(world, "Which cities are cheapest to study in?")
    text = body["reply"]
    assert "Johor Bahru" in text and "BDT 40,820.00" in text
    assert "monthly budget" in text
    assert body["guard"]["status"] == "passed"


def test_the_assistant_never_calls_the_figures_real_or_legal(world: World) -> None:
    text = ask(world, "Is rent in London really GBP 850? Is that legal?")["reply"]
    assert "I cannot say whether something is legal or within a limit" in text
    assert "not a survey" in text and "Indicative. Confirm with your AD bank." in text
    assert "guaranteed" not in text.lower() and "official figure" not in text.lower()


def test_the_arrival_guide_lists_the_steps_by_stage_for_the_country(world: World) -> None:
    body = ask(world, "What should I do when I arrive in Germany?")
    text = body["reply"]
    for stage in ("Before you fly", "In your first week", "In your first month"):
        assert stage in text
    assert "Register your address (Anmeldung)" in text
    assert "Open a student bank account" in text
    assert "Student guide" in text and "Indicative. Confirm with your AD bank." in text
    assert body["guard"]["status"] == "passed"
    assert set(numbers_in(text)) <= fact_numbers(body)
    assert body["understanding"]["intent"] == "ARRIVAL"


def test_without_a_country_the_general_list_is_given_and_the_country_is_asked_for(
    world: World,
) -> None:
    text = ask(world, "What should I do when I arrive?")["reply"]
    assert "general list" in text.lower() and "tell me the country" in text.lower()
    assert "Open a student bank account" in text


def test_the_country_of_an_open_quote_is_used_when_the_message_names_none(world: World) -> None:
    quote = world.quote()  # GBP to the United Kingdom
    text = ask(world, "What should I do before I fly?", quote_id=quote["quote_id"])["reply"]
    assert "United Kingdom" in text and "Check how you receive your visa documents" in text


def test_asking_creates_nothing_and_changes_nothing(world: World) -> None:
    before = len(world.audit_rows(action="quote.created"))
    ask(world, "What is the rent in Berlin?")
    ask(world, "What should I do when I arrive in Canada?")
    assert len(world.audit_rows(action="quote.created")) == before
    assert world.call("GET", "/payments").json()["items"] == []


def test_the_trained_reader_cannot_turn_these_into_something_else(tmp_path: Path) -> None:
    if load_reader("auto") is None:
        pytest.skip("the trained reader is not available")
    world = World(tmp_path, nlu_mode="auto")
    try:
        cost = ask(world, "What is the rent in Manchester?")
        assert cost["understanding"]["intent"] == "COSTS"
        assert "rent GBP 600.00" in cost["reply"]
        arrival = ask(world, "What should I do when I arrive in Germany?")
        assert arrival["understanding"]["intent"] == "ARRIVAL"
        assert "Anmeldung" in arrival["reply"]
    finally:
        world.close()


@pytest.mark.parametrize(
    "message",
    [
        "I want to settle the rent bill (AUD 9800) for my niece before tomorrow!",
        "Hi StudyRoute, I have to pay food and rent by 15 December thanks in advance.",
        "plan my food and rent transfers: $900 per month for two months",
        "is it cheaper to send my daughter's rent monthly or in one go?",
        "we have to pay usd 22,750 rent for the semester starting 23 october 2026 please help.",
        "What documents are needed for a rent payment?",
        "In which countries can I get a card?",
        "Which student bank account has the best interest rate in Canada?",
        "Sir, my landlord is raising my rent, can I refuse? thanks in advance.",
    ],
)
def test_a_payment_request_or_other_question_that_mentions_rent_is_not_a_student_question(
    message: str,
) -> None:
    """These words are common in real payment requests, so they must never start a student answer."""
    assert intent_of(message) not in (Intent.COSTS, Intent.ARRIVAL)
    assert intent_of(message, has_context=True) not in (Intent.COSTS, Intent.ARRIVAL)


def test_no_example_the_assistant_was_trained_and_measured_on_is_taken_for_a_student_question() -> (
    None
):
    """The labelled sets (payment requests, send plans, attacks, out-of-scope text) hold no student
    questions, so none of them may be routed to the student answers: that would change the measured
    behaviour of the assistant (docs/AI_EVALUATION.md)."""
    root = Path(__file__).resolve().parents[2] / "ml" / "data" / "generated"
    sets = sorted(root.glob("*.jsonl.gz"))
    if not sets:
        pytest.skip("the generated datasets are not in this checkout")
    caught: list[str] = []
    for path in sets:
        with gzip.open(path, "rt", encoding="utf-8") as handle:
            for line in handle:
                text = json.loads(line)["text"]
                parsed = parse_request(text, ["GBP", "USD", "EUR", "AUD", "CAD", "MYR"], TODAY)
                if choose_intent(text, parsed, has_context=False) in (Intent.COSTS, Intent.ARRIVAL):
                    caught.append(f"{path.stem}: {text[:90]}")
    assert caught == []
