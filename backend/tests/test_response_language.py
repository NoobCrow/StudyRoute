"""Current-turn language selection, independent of old chat language."""

import pytest

from app.ai.prompt import response_language


@pytest.mark.parametrize(
    ("message", "expected"),
    [
        ("What documents do I need?", "English"),
        ("I need to pay GBP 10,000 tuition by 28 October", "English"),
        ("How often should I send GBP 800 a month for 9 months?", "English"),
        ("Why is Provider B cheaper than A?", "English"),
        ("আমার কী নথি লাগবে?", "Bengali"),
        ("amake kivabe help korbe?", "Banglish (Bengali written in Latin letters)"),
        ("What documents do I need? Reply in Bengali", "Bengali"),
        ("আমার কী নথি লাগবে? Reply in English", "English"),
    ],
)
def test_current_turn_language(message: str, expected: str) -> None:
    assert response_language(message) == expected
