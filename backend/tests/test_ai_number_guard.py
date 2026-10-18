from decimal import Decimal

from app.ai.facts import FactSet
from app.ai.number_guard import check_numbers, numbers_in


def test_numbers_are_extracted_with_separators_and_percentages() -> None:
    text = "Total BDT 25,300.00 is 1.58% on 2026-10-28, see fact_17 and prov_b2."
    assert numbers_in(text) == [
        Decimal("25300.00"), Decimal("1.58"), Decimal("2026"), Decimal("10"), Decimal("28"),
    ]  # fmt: skip


def test_identifiers_glued_to_letters_are_not_numbers() -> None:
    assert numbers_in("7c1d4f0e-5a9b pay_01HZXA qte_9 T+3d") == []


def test_values_are_compared_numerically_not_textually() -> None:
    facts = FactSet()
    facts.add("a", "total", "BDT 25,300.00")
    assert check_numbers("It costs BDT 25,300 in total.", facts.numbers()).ok
    assert check_numbers("It costs 25300.0 in total.", facts.numbers()).ok


def test_an_invented_number_is_reported() -> None:
    facts = FactSet()
    facts.add("cost", "Provider B cost", "1.58%")
    result = check_numbers("Provider B costs 3.99% and 1.58%.", facts.numbers())
    assert not result.ok
    assert result.offending == ("3.99",)


def test_text_without_numbers_always_passes() -> None:
    assert check_numbers("Use OUR for tuition. Confirm with your AD bank.", set()).ok
