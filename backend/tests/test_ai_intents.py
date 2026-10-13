import pytest

from app.ai.intents import Intent, classify, mentioned_providers

IDS = ["prov_a", "prov_b", "prov_c"]


@pytest.mark.parametrize(
    ("message", "intent"),
    [
        ("Why is Provider B cheaper than A?", Intent.COMPARE),
        ("Which provider is cheapest?", Intent.COMPARE),
        ("What do OUR, SHA and BEN mean?", Intent.CHARGES),
        ("Explain the shortfall warning on Provider C", Intent.CHARGES),
        ("When should I send the payment?", Intent.DEADLINE),
        ("What documents do I need for UK tuition?", Intent.CHECKLIST),
        ("What is the daily limit?", Intent.LIMITS),
        ("What is my KYC status?", Intent.KYC),
        ("Where is my payment?", Intent.STATUS),
        ("Create a draft with Provider B", Intent.DRAFT),
        ("Please request approval for it", Intent.REQUEST_APPROVAL),
        ("hello", Intent.HELP),
    ],
)
def test_classify(message: str, intent: Intent) -> None:
    assert classify(message) is intent


def test_providers_are_found_in_order_of_appearance() -> None:
    assert mentioned_providers("Why is Provider B cheaper than A?", IDS) == ["prov_b", "prov_a"]
    assert mentioned_providers("compare prov_c and provider a", IDS) == ["prov_c", "prov_a"]
    assert mentioned_providers("A quote please", IDS) == []
    assert mentioned_providers("Provider Z is unknown", IDS) == []
