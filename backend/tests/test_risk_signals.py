"""The review signals are plain rules: same facts in, same signals out, and never a verdict."""

from __future__ import annotations

import pytest

from app.domain.review_text import SIGNAL_TEXT, STATUS_TEXT
from app.engine import risk_signals as rs

PARAMS = rs.ReviewParams(large_usd_minor=4_000_000, split_min_payments=3, split_window_days=7)


def facts(**overrides: object) -> rs.ReviewFacts:
    base: dict[str, object] = {
        "amount_usd_minor": 1_300_000,
        "earlier_usd_minor": (),
        "recipient_first_payment": False,
        "recipient_name_flagged": False,
        "has_invoice_on_file": True,
        "purpose": "TUITION",
    }
    base.update(overrides)
    return rs.ReviewFacts(**base)  # type: ignore[arg-type]


def codes(found: list[rs.Signal]) -> list[str]:
    return [s.code for s in found]


def test_an_ordinary_payment_has_no_signals() -> None:
    assert rs.find_signals(facts(), PARAMS) == []


def test_the_large_amount_line_is_inclusive() -> None:
    assert codes(rs.find_signals(facts(amount_usd_minor=3_999_999), PARAMS)) == []
    found = rs.find_signals(facts(amount_usd_minor=4_000_000), PARAMS)
    assert codes(found) == [rs.LARGE_AMOUNT] and found[0].needs_human
    assert found[0].figures == {"amount": "USD 40,000.00", "line": "USD 40,000.00"}


def test_several_smaller_payments_that_add_up_past_the_line_are_a_possible_split() -> None:
    found = rs.find_signals(
        facts(amount_usd_minor=1_500_000, earlier_usd_minor=(1_400_000, 1_300_000)), PARAMS
    )
    assert codes(found) == [rs.POSSIBLE_SPLIT]
    assert found[0].figures["payments"] == "3" and found[0].figures["total"] == "USD 42,000.00"


def test_two_payments_or_a_small_total_are_not_a_split() -> None:
    assert not rs.find_signals(
        facts(amount_usd_minor=2_500_000, earlier_usd_minor=(2_500_000,)), PARAMS
    )
    assert not rs.find_signals(
        facts(amount_usd_minor=100_000, earlier_usd_minor=(100_000, 100_000)), PARAMS
    )


def test_a_large_payment_is_not_also_called_a_split() -> None:
    found = rs.find_signals(facts(amount_usd_minor=4_500_000, earlier_usd_minor=(100, 100)), PARAMS)
    assert codes(found) == [rs.LARGE_AMOUNT]


def test_context_signals_do_not_need_a_person_but_a_flagged_name_does() -> None:
    found = rs.find_signals(facts(recipient_first_payment=True, has_invoice_on_file=False), PARAMS)
    assert codes(found) == [rs.NEW_RECIPIENT, rs.NO_INVOICE]
    assert not rs.needs_human(found)
    assert rs.needs_human(rs.find_signals(facts(recipient_name_flagged=True), PARAMS))


def test_a_missing_invoice_only_matters_for_tuition() -> None:
    assert not rs.find_signals(facts(purpose="LIVING", has_invoice_on_file=False), PARAMS)


@pytest.mark.parametrize("code", [rs.LARGE_AMOUNT, rs.POSSIBLE_SPLIT, rs.NAME_CHECK,
                                  rs.NEW_RECIPIENT, rs.NO_INVOICE])  # fmt: skip
def test_every_signal_has_plain_words_for_the_parent_and_a_check_for_the_reviewer(
    code: str,
) -> None:
    text = SIGNAL_TEXT[code]
    assert text["title"] and text["parent_means"] and text["parent_why"]
    assert text["prepare"] and text["reviewer_check"]


def test_every_status_has_a_headline_and_a_sentence() -> None:
    assert set(STATUS_TEXT) == {"CLEARED_AUTO", "OPEN", "INFO_REQUESTED", "CLEARED", "DECLINED"}
    assert all(entry["headline"] and entry["parent"] for entry in STATUS_TEXT.values())


def test_no_text_accuses_anyone() -> None:
    blob = (str(SIGNAL_TEXT) + str(STATUS_TEXT)).lower()
    for word in ("launder", "criminal", "illegal", "fraud", "suspicious", "guilty"):
        assert word not in blob, word
