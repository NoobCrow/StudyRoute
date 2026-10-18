"""The quote knows the deadline: it names the cheapest provider that arrives in time.

The fake clock starts on Wednesday 14 October 2026, so the earliest send date is today. The
synthetic providers settle in 1 (A), 2 (B) and 3 (C) business days, counting only days that both
Bangladesh and the UK work.
"""

from __future__ import annotations

from tests.helpers import World


def test_a_comfortable_deadline_keeps_the_cheapest_provider(world: World) -> None:
    quote = world.quote(due_date="2026-10-28")
    fit = quote["deadline_fit"]
    assert fit["best_in_time"] == fit["cheapest_overall"] == quote["results"][0]["provider_id"]
    assert fit["cheapest_misses_deadline"] is False
    assert all(p["meets_deadline"] for p in fit["providers"])
    assert fit["send_date"] == "2026-10-14" and fit["due_date"] == "2026-10-28"


def test_a_tight_deadline_passes_over_the_cheapest_provider(world: World) -> None:
    quote = world.quote(due_date="2026-10-15")
    fit = quote["deadline_fit"]
    assert quote["results"][0]["provider_id"] == "prov_b"
    assert fit["cheapest_overall"] == "prov_b"
    assert fit["best_in_time"] == "prov_a"
    assert fit["cheapest_misses_deadline"] is True
    by_id = {p["provider_id"]: p for p in fit["providers"]}
    assert by_id["prov_a"]["arrives_on"] == "2026-10-15" and by_id["prov_a"]["meets_deadline"]
    assert by_id["prov_b"]["meets_deadline"] is False and by_id["prov_b"]["days_to_spare"] < 0


def test_when_nobody_can_arrive_in_time_there_is_no_best_provider(world: World) -> None:
    fit = world.quote(due_date="2026-10-14")["deadline_fit"]
    assert fit["best_in_time"] is None
    assert fit["fastest"] == "prov_a"
    assert "Indicative" in fit["indicative"]


def test_without_a_due_date_there_is_no_deadline_fit(world: World) -> None:
    assert world.quote(due_date=None)["deadline_fit"] is None


def test_the_fit_does_not_change_the_numbers_or_the_quote_hash(world: World) -> None:
    with_deadline = world.quote(due_date="2026-10-15")
    without = world.quote(due_date=None)
    assert with_deadline["results"] == without["results"]
    assert with_deadline["input_hash"] == without["input_hash"]


def test_the_fit_is_also_returned_when_the_quote_is_read_again(world: World) -> None:
    quote = world.quote(due_date="2026-10-15")
    again = world.call("GET", f"/quotes/{quote['quote_id']}").json()
    assert again["deadline_fit"] == quote["deadline_fit"]
