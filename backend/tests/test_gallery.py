"""app/scripts/gallery.py: the parts that are plain logic (the photographs need a browser)."""

from __future__ import annotations

from app.engine.validators import is_valid_iban
from app.scripts.gallery import SLOW_RECIPIENT, iban_gb, say


def test_the_generated_iban_has_correct_check_digits() -> None:
    for account in ("00007777", "00005555", "12344821"):
        assert is_valid_iban(iban_gb(account)), account


def test_the_generated_iban_is_for_the_invented_bank_in_the_united_kingdom() -> None:
    iban = iban_gb("00007777")
    assert iban.startswith("GB") and "EXMP" in iban and iban.endswith("00007777")


def test_a_changed_digit_in_the_generated_iban_is_caught_by_the_validator() -> None:
    good = iban_gb("00007777")
    assert not is_valid_iban(good[:-1] + ("8" if good[-1] != "8" else "9"))


def test_saying_something_to_the_assistant_waits_for_that_many_answers() -> None:
    steps = say("Why is Provider B cheaper than A?", 2)
    assert steps[0]["type"]["text"] == "Why is Provider B cheaper than A?"
    assert steps[0]["type"]["enter"] is True
    assert steps[1] == {"waitText": "How I read this", "count": 2}


def test_the_slow_payment_uses_the_scenario_name_the_simulator_knows() -> None:
    assert "SLOW_TEST" in SLOW_RECIPIENT
