"""Stretch features: F9 runway, F10 rate hint and F11 multi-corridor."""

from __future__ import annotations

from typing import Any

import pytest

from tests.helpers import World

CORRIDORS = [
    ("GB", "GBP", {"iban": "GB08EXMP12345612344821"}, "EXMPGB2L"),
    ("DE", "EUR", {"iban": "DE54370400440532013048"}, "EXMPDEFF"),
    ("US", "USD", {"routing_code": "123456780", "account_number": "000123456789"}, "EXMPUS33"),
    ("AU", "AUD", {"account_number": "123456789"}, "EXMPAU2S"),
    ("CA", "CAD", {"account_number": "0012345678"}, "EXMPCAT2"),
    ("MY", "MYR", {"account_number": "1234567890123"}, "EXMPMYKL"),
]
RUNWAY = "/planner/runway?amount_minor=1000000&monthly_cost_minor=150000&currency=GBP"


def test_runway_endpoint_rounds_down_and_shows_an_unverified_reference(world: World) -> None:
    body = world.call("GET", RUNWAY).json()
    assert body["display"]["covers"] == "6.6 months"
    assert body["display"]["leftover"] == "GBP 1,000.00"
    assert body["monthly_cost_usd_equivalent"] == "USD 1,967.21"
    assert body["reference"]["badge"] == "NOT_VERIFIED"
    assert "Confirm with your AD bank" in body["reference"]["note"]
    assert world.call("GET", RUNWAY.replace("GBP", "XYZ")).status_code == 422
    zero = RUNWAY.replace("monthly_cost_minor=150000", "monthly_cost_minor=0")
    assert world.call("GET", zero).status_code == 422


def test_rate_history_is_synthetic_deterministic_and_carries_a_hint(world: World) -> None:
    first = world.call("GET", "/rates/history?currency=GBP").json()
    second = world.call("GET", "/rates/history?currency=GBP").json()
    assert first == second
    assert first["source"] == "synthetic"
    assert len(first["points"]) == 30
    assert first["points"][-1] == {"date": "2026-10-14", "rate": "160.000000"}
    assert "not a forecast" in first["hint"]["message"].lower()
    assert first["hint"]["kind"] in {"SEND_NOW", "WAIT_MAY_HELP", "NEUTRAL"}
    short = world.call("GET", "/rates/history?currency=USD&days=10").json()
    assert len(short["points"]) == 10
    assert world.call("GET", "/rates/history?currency=XYZ").status_code == 422
    assert world.call("GET", "/rates/history?days=3").status_code == 422


@pytest.mark.parametrize(("country", "currency", "account", "bic"), CORRIDORS)
def test_F11_every_corridor_can_quote_add_a_recipient_and_draft(
    world: World, country: str, currency: str, account: dict[str, Any], bic: str
) -> None:
    quote = world.quote(
        target={"amount_minor": 500_000, "currency": currency},
        destination_country=country,
        due_date=None,
    )
    assert quote["target"]["currency"] == currency
    assert len(quote["results"]) == 3
    body = {
        "type": "UNIVERSITY",
        "display_name": f"{country} Test University (synthetic)",
        "country": country,
        "bic": bic,
        **account,
    }
    created = world.call("POST", "/recipients", json=body)
    assert created.status_code == 201, created.text
    draft = world.call(
        "POST",
        "/payments",
        idem=True,
        json={
            "quote_id": quote["quote_id"],
            "provider_id": "prov_b",
            "recipient_id": created.json()["recipient_id"],
            "reference": "INV-1",
        },
    )
    assert draft.status_code == 201, draft.text
    assert draft.json()["target"]["currency"] == currency


@pytest.mark.parametrize("country", [c[0] for c in CORRIDORS])
@pytest.mark.parametrize("purpose", ["TUITION", "LIVING"])
def test_F11_every_corridor_has_a_checklist_and_a_planner_calendar(
    world: World, country: str, purpose: str
) -> None:
    checklist = world.call("GET", f"/checklist?country={country}&purpose={purpose}").json()
    assert checklist["items"]
    assert checklist["verified"] is False
    plan = world.call("GET", f"/planner/deadline?due_date=2026-11-20&country={country}")
    assert plan.status_code == 200
    assert plan.json()["latest_send_date"] < "2026-11-20"


def test_F11_a_recipient_in_another_country_than_the_quote_is_refused(world: World) -> None:
    quote = world.quote(
        target={"amount_minor": 500_000, "currency": "EUR"}, destination_country="DE"
    )
    response = world.call(
        "POST",
        "/payments",
        idem=True,
        json={
            "quote_id": quote["quote_id"],
            "provider_id": "prov_b",
            "recipient_id": world.recipient_id(),
            "reference": "INV-1",
        },
    )
    assert response.status_code == 422


def test_the_us_quote_uses_the_synthetic_usd_rate(world: World) -> None:
    target = {"amount_minor": 1_000_000, "currency": "USD"}
    quote = world.quote(target=target, destination_country="US")
    assert quote["mid_rate"]["value"] == "122.000000"
    assert quote["mid_rate"]["source"] == "synthetic"
    assert quote["mid_rate"]["display"] == "BDT 122.000000 per 1 USD (synthetic)"
