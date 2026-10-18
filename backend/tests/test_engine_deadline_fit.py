"""Deadline fit: the cheapest provider that ARRIVES before the due date, not just the cheapest.

Hand-worked case (calendars as in the planner tests). A business day is a day both countries
work, so the working week is Monday to Thursday (Bangladesh rests Friday and Saturday, the UK
Saturday and Sunday). Sent on Wednesday 14 October 2026:

    eta 1 business day  arrives Thursday 15 October
    eta 2 business days arrives Monday    19 October (Friday, Saturday and Sunday are skipped)
    eta 3 business days arrives Tuesday   20 October
"""

from dataclasses import dataclass
from datetime import date

import pytest

from app.engine.deadline_fit import add_business_days, choose_for_deadline
from app.engine.planner import Calendar, parse_weekdays

BD = Calendar("BD", parse_weekdays(["Fri", "Sat"]), {})
GB = Calendar("GB", parse_weekdays(["Sat", "Sun"]), {})
CALENDARS = [BD, GB]
SEND = date(2026, 10, 14)  # a Wednesday


@dataclass(frozen=True)
class Offer:
    provider_id: str
    eta_business_days: int


# Cheapest first, as the ranking delivers them: C is the cheapest but the slowest.
RANKED = [Offer("prov_c", 3), Offer("prov_b", 2), Offer("prov_a", 1)]


def test_business_days_skip_the_weekend_of_either_country() -> None:
    assert add_business_days(SEND, 0, CALENDARS) == SEND
    assert add_business_days(SEND, 1, CALENDARS) == date(2026, 10, 15)
    assert add_business_days(SEND, 2, CALENDARS) == date(2026, 10, 19)
    assert add_business_days(SEND, 3, CALENDARS) == date(2026, 10, 20)


def test_the_cheapest_that_misses_the_deadline_is_passed_over() -> None:
    choice = choose_for_deadline(
        RANKED, send_date=SEND, due_date=date(2026, 10, 19), calendars=CALENDARS
    )
    assert choice.cheapest_overall == "prov_c"
    assert choice.best_in_time == "prov_b"
    assert choice.cheapest_misses_deadline is True
    fits = {f.provider_id: f for f in choice.fits}
    assert fits["prov_c"].arrives_on == date(2026, 10, 20) and not fits["prov_c"].meets_deadline
    assert fits["prov_c"].days_to_spare == -1
    assert fits["prov_b"].arrives_on == date(2026, 10, 19) and fits["prov_b"].meets_deadline
    assert fits["prov_b"].days_to_spare == 0
    assert fits["prov_a"].days_to_spare == 4


def test_when_the_cheapest_is_in_time_nothing_changes() -> None:
    choice = choose_for_deadline(
        RANKED, send_date=SEND, due_date=date(2026, 10, 27), calendars=CALENDARS
    )
    assert choice.best_in_time == choice.cheapest_overall == "prov_c"
    assert choice.cheapest_misses_deadline is False


def test_when_nobody_arrives_in_time_there_is_no_best_and_the_fastest_is_named() -> None:
    choice = choose_for_deadline(
        RANKED, send_date=SEND, due_date=date(2026, 10, 14), calendars=CALENDARS
    )
    assert choice.best_in_time is None
    assert choice.fastest == "prov_a"
    assert all(not f.meets_deadline for f in choice.fits)


def test_a_provider_that_arrives_on_the_due_date_counts_as_in_time() -> None:
    choice = choose_for_deadline(
        [Offer("only", 1)], send_date=SEND, due_date=date(2026, 10, 15), calendars=CALENDARS
    )
    assert choice.best_in_time == "only"


def test_the_api_dict_is_plain_data_with_the_indicative_note() -> None:
    choice = choose_for_deadline(
        RANKED, send_date=SEND, due_date=date(2026, 10, 19), calendars=CALENDARS
    )
    body = choice.to_api_dict()
    assert body["best_in_time"] == "prov_b" and body["cheapest_overall"] == "prov_c"
    assert body["due_date"] == "2026-10-19" and body["send_date"] == "2026-10-14"
    assert body["providers"][0] == {
        "provider_id": "prov_c",
        "arrives_on": "2026-10-20",
        "meets_deadline": False,
        "days_to_spare": -1,
    }
    assert "Indicative" in body["indicative"]


def test_an_empty_offer_list_has_no_choice() -> None:
    choice = choose_for_deadline(
        [], send_date=SEND, due_date=date(2026, 10, 19), calendars=CALENDARS
    )
    assert (
        choice.best_in_time is None and choice.cheapest_overall is None and choice.fastest is None
    )


def test_a_negative_number_of_days_is_refused() -> None:
    with pytest.raises(ValueError, match="negative"):
        add_business_days(SEND, -1, CALENDARS)
