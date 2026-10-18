"""GET /planner/student-budget and /planner/arrival-guide: the student help over the API."""

from __future__ import annotations

from typing import Any

from tests.helpers import World

INDICATIVE = "Indicative. Confirm with your AD bank."


def budget(world: World, query: str = "", who: str | None = "parent") -> Any:
    return world.call("GET", f"/planner/student-budget?{query}", who)


def arrival(world: World, country: str = "GB", who: str | None = "parent") -> Any:
    return world.call("GET", f"/planner/arrival-guide?country={country}", who)


def city(body: dict[str, Any], name: str) -> dict[str, Any]:
    return next(row for row in body["items"] if row["city"] == name)


# --- the student budget ------------------------------------------------------------------


def test_every_city_is_listed_from_the_cheapest_month_in_taka(world: World) -> None:
    body = budget(world).json()
    assert body["housing"] == "shared"
    assert len(body["items"]) == 20
    totals = [row["total_bdt"]["amount_minor"] for row in body["items"]]
    assert totals == sorted(totals)
    assert [c["country"] for c in body["countries"]] == ["AU", "CA", "DE", "GB", "MY", "US"]
    assert body["budget"] is None
    assert all(row["fits"] is None for row in body["items"])


def test_a_month_in_london_is_added_up_and_converted_by_the_engine(world: World) -> None:
    london = city(budget(world).json(), "London")
    assert [line["key"] for line in london["lines"]] == [
        "rent",
        "food",
        "transport",
        "utilities",
        "phone_internet",
        "other",
    ]
    assert london["total"]["formatted"] == "GBP 1,605.00"
    assert london["total_bdt"]["formatted"] == "BDT 256,800.00"
    assert london["rent_bdt"]["formatted"] == "BDT 136,000.00"
    assert london["rent_share_pct"] == "53.0"
    assert london["rate_bdt_per_unit"] == "160.000000"
    assert london["country_name"] == "United Kingdom"


def test_a_studio_changes_only_the_rent(world: World) -> None:
    shared = city(budget(world, "housing=shared").json(), "London")
    studio = city(budget(world, "housing=studio").json(), "London")
    assert studio["housing"] == "studio"
    assert studio["lines"][0]["formatted"] == "GBP 1,500.00"
    assert studio["total"]["formatted"] == "GBP 2,255.00"
    assert studio["lines"][1:] == shared["lines"][1:]


def test_a_monthly_budget_marks_which_cities_fit_and_by_how_much(world: World) -> None:
    body = budget(world, "budget_bdt_minor=20000000").json()  # BDT 200,000.00
    assert body["budget"]["formatted"] == "BDT 200,000.00"
    manchester, london = city(body, "Manchester"), city(body, "London")
    assert manchester["total_bdt"]["formatted"] == "BDT 191,200.00"
    assert manchester["fits"] is True
    assert manchester["spare_bdt"]["formatted"] == "BDT 8,800.00" and manchester["gap_bdt"] is None
    assert london["fits"] is False
    assert london["gap_bdt"]["formatted"] == "BDT 56,800.00" and london["spare_bdt"] is None
    fitting = [row for row in body["items"] if row["fits"]]
    assert body["summary"]["fitting"] == len(fitting) > 0
    assert body["summary"]["cities"] == 20
    assert body["summary"]["cheapest"]["city"] == body["items"][0]["city"]


def test_a_budget_that_equals_the_month_fits_exactly(world: World) -> None:
    exact = city(budget(world).json(), "Manchester")["total_bdt"]["amount_minor"]
    on_the_line = city(budget(world, f"budget_bdt_minor={exact}").json(), "Manchester")
    assert on_the_line["fits"] is True and on_the_line["spare_bdt"]["amount_minor"] == 0
    short = city(budget(world, f"budget_bdt_minor={exact - 1}").json(), "Manchester")
    assert short["fits"] is False and short["gap_bdt"]["amount_minor"] == 1


def test_one_country_can_be_asked_for_on_its_own(world: World) -> None:
    body = budget(world, "country=DE").json()
    assert {row["country"] for row in body["items"]} == {"DE"}
    assert [row["city"] for row in body["items"]] == ["Leipzig", "Berlin", "Munich"]


def test_a_country_with_no_figures_is_refused_not_guessed(world: World) -> None:
    response = budget(world, "country=FR")
    assert response.status_code == 422
    assert response.json()["code"] == "VALIDATION_FAILED"
    assert "France" in response.json()["detail"] or "FR" in response.json()["detail"]


def test_the_figures_are_labelled_invented_and_not_verified(world: World) -> None:
    body = budget(world).json()
    assert body["synthetic"] is True
    assert body["source"]["verified"] is False and body["source"]["badge"] == "NOT_VERIFIED"
    assert body["source"]["source_url"].startswith("https://")
    assert INDICATIVE in body["disclaimer"]
    assert "not a survey" in body["disclaimer"]
    assert "own estimate" in body["disclaimer"]


def test_the_budget_may_be_read_by_a_parent_or_a_student_but_not_the_reviewer(world: World) -> None:
    assert budget(world, who="student").status_code == 200
    assert budget(world, who="admin").status_code == 403
    assert budget(world, who=None).status_code == 401


def test_bad_budget_inputs_are_validation_failures(world: World) -> None:
    for query in (
        "budget_bdt_minor=0",
        "budget_bdt_minor=-5",
        "budget_bdt_minor=abc",
        "budget_bdt_minor=10000000000000",
        "housing=castle",
        "country=gb",
        "country=GBR",
    ):
        assert budget(world, query).status_code == 422, query


# --- the arrival guide -------------------------------------------------------------------


def test_the_guide_has_three_stages_in_order_with_a_hint_on_every_step(world: World) -> None:
    body = arrival(world, "GB").json()
    assert body["country"] == "GB" and body["country_name"] == "United Kingdom"
    assert [s["key"] for s in body["stages"]] == ["before", "first_week", "first_month"]
    assert [s["label"] for s in body["stages"]] == [
        "Before you fly",
        "In your first week",
        "In your first month",
    ]
    for stage in body["stages"]:
        assert stage["items"], stage["key"]
        for item in stage["items"]:
            assert item["key"] and item["label"] and item["hint"]
    keys = {i["key"] for s in body["stages"] for i in s["items"]}
    assert {"accommodation", "student_account", "gb_visa_documents", "gb_doctor"} <= keys
    assert body["general"] is False
    assert body["item_count"] == len(keys)


def test_each_country_adds_its_own_steps_and_drops_those_that_do_not_apply(world: World) -> None:
    def keys(country: str) -> set[str]:
        return {i["key"] for s in arrival(world, country).json()["stages"] for i in s["items"]}

    assert "de_register_address" in keys("DE") and "register_address" not in keys("DE")
    assert "au_oshc" in keys("AU") and "health_cover" not in keys("AU")
    assert "us_i20" in keys("US") and "ca_sin" in keys("CA")
    assert "my_student_pass" in keys("MY")


def test_a_country_without_its_own_list_gets_the_general_one_and_says_so(world: World) -> None:
    body = arrival(world, "FR").json()
    assert body["general"] is True
    assert "general list" in body["note"]
    assert body["country_name"] == "France"
    assert len(body["stages"]) == 3


def test_the_guide_is_labelled_indicative_and_not_verified(world: World) -> None:
    body = arrival(world, "GB").json()
    assert body["verified"] is False and body["badge"] == "NOT_VERIFIED"
    assert body["source_url"].startswith("https://")
    assert body["indicative"] == INDICATIVE
    assert "confirm" in body["note"].lower()


def test_an_unknown_country_code_is_a_validation_failure(world: World) -> None:
    assert arrival(world, "ZZ").status_code == 422
    assert arrival(world, "gb").status_code == 422
    assert arrival(world, "GBR").status_code == 422


def test_the_guide_may_be_read_by_a_parent_or_a_student_but_not_the_reviewer(world: World) -> None:
    assert arrival(world, who="student").status_code == 200
    assert arrival(world, who="admin").status_code == 403
    assert arrival(world, who=None).status_code == 401


def test_reading_either_guide_writes_nothing_to_the_audit_log(world: World) -> None:
    budget(world)  # the first call signs the parent in, which is audited
    before = len(world.audit_rows())
    budget(world)
    arrival(world)
    assert len(world.audit_rows()) == before
