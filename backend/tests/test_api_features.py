"""Planner, checklist, documents, tracker, instruction preview, listings and data reset."""

from __future__ import annotations

from tests.helpers import World


def test_planner_endpoint_works_back_from_the_due_date_for_both_calendars(world: World) -> None:
    body = world.call("GET", "/planner/deadline?due_date=2026-10-28&country=GB").json()
    assert body["latest_send_date"] == "2026-10-20"
    assert body["recommended_send_date"] == "2026-10-19"
    assert body["earliest_send_date"] == "2026-10-14"
    assert body["status"] == "ON_TRACK"
    assert body["indicative"] == "Indicative. Confirm with your AD bank."
    assert "KYC_PENDING" in {w["code"] for w in body["warnings"]}
    assert world.call("GET", "/planner/deadline?due_date=2026-10-28&country=ZZ").status_code == 422
    assert world.call("GET", "/planner/deadline?due_date=garbage").status_code == 422


def test_planner_warns_about_an_expired_quote_and_late_sending(world: World) -> None:
    quote = world.quote()
    world.clock.advance(301)
    path = f"/planner/deadline?due_date=2026-10-28&country=GB&quote_id={quote['quote_id']}"
    assert "QUOTE_EXPIRED" in {w["code"] for w in world.call("GET", path).json()["warnings"]}
    world.clock.advance(9 * 24 * 3600)
    late = world.call("GET", "/planner/deadline?due_date=2026-10-28&country=GB").json()
    assert late["status"] == "LATE"


def test_checklist_is_indicative_and_marks_provided_documents(world: World) -> None:
    body = world.call("GET", "/checklist?country=GB&purpose=TUITION").json()
    keys = [i["key"] for i in body["items"]]
    assert keys[:3] == ["offer_letter", "fee_demand_note", "passport"]
    assert body["verified"] is False
    assert "Confirm with your AD bank" in body["indicative"]
    assert not any(i["provided"] for i in body["items"])
    added = world.call(
        "POST", "/documents", json={"kind": "offer_letter", "filename": "C:\\fake\\offer.txt"}
    )
    assert added.status_code == 201
    assert added.json()["filename"] == "offer.txt"
    after = world.call("GET", "/checklist?country=GB&purpose=TUITION").json()
    assert [i["key"] for i in after["items"] if i["provided"]] == ["offer_letter"]
    assert world.call("GET", "/checklist?country=GB&purpose=NOPE").status_code == 422


def test_documents_can_be_added_listed_and_removed_with_audit_events(world: World) -> None:
    doc = world.call(
        "POST", "/documents",
        json={"kind": "fee_demand_note", "filename": "fees.txt", "content_text": "Tuition: GBP 10000"},
    ).json()  # fmt: skip
    assert doc["has_content"] and doc["mock"] is True
    assert world.call("GET", "/documents").json()["items"][0]["document_id"] == doc["document_id"]
    assert world.call("DELETE", f"/documents/{doc['document_id']}").status_code == 200
    assert world.call("GET", "/documents").json()["items"] == []
    actions = [r["action"] for r in world.audit_rows()]
    assert "document.added" in actions and "document.removed" in actions


def test_documents_reject_unknown_kinds_and_huge_text(world: World) -> None:
    assert world.call("POST", "/documents", json={"kind": "x", "filename": "a"}).status_code == 422
    huge = {"kind": "passport", "filename": "a.txt", "content_text": "x" * 20_001}
    assert world.call("POST", "/documents", json=huge).status_code == 422
    assert (
        world.call(
            "POST", "/documents", "admin", json={"kind": "passport", "filename": "a"}
        ).status_code
        == 403
    )


def test_instruction_preview_shows_mt103_fields_masked_and_simulated(world: World) -> None:
    payment = world.draft()
    body = world.call("GET", f"/payments/{payment['payment_id']}/instruction-preview").json()
    fields = {f["tag"]: f["value"] for f in body["fields"]}
    assert fields[":71A:"] == "OUR"
    assert fields[":70:"] == "INV-2026-4471 / STU-883201"
    assert fields[":32A:"] == "261028GBP10000,00"
    assert fields[":57A:"] == "EXMPGB2L"
    assert "GB** **** 4821" in fields[":59:"]
    assert "GB08EXMP" not in str(body)
    assert "Demo Parent" in fields[":50K:"]
    assert body["simulated"] is True
    assert body["pacs008"]["ChrgBr"] == "DEBT"


def test_the_tracker_starts_with_the_draft_history_and_names_the_host_rail(world: World) -> None:
    payment = world.draft()
    tracker = world.call("GET", f"/payments/{payment['payment_id']}/tracker").json()
    assert [t["state"] for t in tracker["timeline"]] == ["DRAFT", "QUOTED"]
    assert tracker["uetr"] is None
    assert "Faster Payments" in tracker["host_rail"]
    assert tracker["simulated"] is True


def test_payment_listing_paginates_with_a_cursor(world: World) -> None:
    for n in range(3):
        world.clock.advance(1)
        world.draft(reference=f"INV-{n}")
    first = world.call("GET", "/payments?limit=2").json()
    assert len(first["items"]) == 2 and first["next_cursor"]
    second = world.call("GET", f"/payments?limit=2&cursor={first['next_cursor']}").json()
    assert len(second["items"]) == 1 and second["next_cursor"] is None
    refs = [p["reference"] for p in first["items"] + second["items"]]
    assert refs == ["INV-2", "INV-1", "INV-0"]
    assert world.call("GET", "/payments?limit=2&cursor=garbage").status_code == 400


def test_reset_my_data_removes_business_data_but_keeps_the_audit_chain(world: World) -> None:
    world.ready_payment()
    before = world.call("GET", "/audit/verify", "admin").json()["events_checked"]
    assert world.call("POST", "/me/reset", "student").status_code == 403
    response = world.call("POST", "/me/reset")
    assert response.status_code == 200
    assert response.json()["deleted"]["payments"] == 1
    assert world.call("GET", "/payments").json()["items"] == []
    assert world.call("GET", "/recipients").json()["items"] == []
    after = world.call("GET", "/audit/verify", "admin").json()
    assert after["status"] == "PASS"
    assert after["events_checked"] > before
    assert len(world.audit_rows(action="user.data_reset")) == 1


def test_corridors_listing_shows_all_six_destinations(world: World) -> None:
    items = world.call("GET", "/corridors").json()["items"]
    assert {c["country"] for c in items} == {"GB", "US", "DE", "AU", "CA", "MY"}
    assert next(c for c in items if c["country"] == "GB")["currency"] == "GBP"
