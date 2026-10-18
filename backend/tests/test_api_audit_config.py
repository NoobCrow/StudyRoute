"""Audit endpoints (T16 through the API) and the admin rules configuration."""

from __future__ import annotations

import json
from pathlib import Path

from app.scripts.tamper_audit import restore_row, tamper_row
from tests.helpers import World


def db_file(world: World) -> Path:
    return Path(world.ctx.db.sqlite_path())


def test_T16_editing_an_audit_row_makes_verify_fail_at_that_sequence(world: World) -> None:
    approval = world.ready_payment()
    world.approve(approval)
    ok = world.call("GET", "/audit/verify", "admin").json()
    assert ok["status"] == "PASS"
    assert ok["events_checked"] > 10

    target = ok["events_checked"] - 3
    tamper_row(db_file(world), target)
    bad = world.call("GET", "/audit/verify", "admin").json()
    assert bad["status"] == "FAIL"
    assert bad["failed_seq"] == target
    assert bad["reason"] == "HASH_MISMATCH"

    restore_row(db_file(world))
    assert world.call("GET", "/audit/verify", "admin").json()["status"] == "PASS"


def test_verify_accepts_an_externally_published_head(world: World) -> None:
    head = world.call("GET", "/audit/verify", "admin").json()["head"]["hash"]
    assert (
        world.call("GET", f"/audit/verify?expected_head={head}", "admin").json()["status"] == "PASS"
    )
    wrong = world.call("GET", f"/audit/verify?expected_head={'0' * 64}", "admin").json()
    assert wrong["status"] == "FAIL"
    assert wrong["reason"] == "EXTERNAL_HEAD_MISMATCH"


def test_only_an_admin_can_verify_and_parents_see_only_their_own_events(world: World) -> None:
    approval = world.ready_payment()
    assert world.call("GET", "/audit/verify", "parent").status_code == 403
    assert world.call("GET", "/audit/verify", "student").status_code == 403
    assert world.call("GET", "/audit/events", "student").status_code == 403
    mine = world.call("GET", "/audit/events?limit=100", "parent").json()
    assert mine["scope"] == "your events"
    everything = world.call("GET", "/audit/events?limit=100", "admin").json()
    assert everything["scope"] == "all events"
    assert len(everything["items"]) >= len(mine["items"]) > 0
    mine_ids = {e["event_id"] for e in mine["items"]}
    assert all(
        e["actor_id"] == world.ids["parent"] or e["payment_id"] == approval["payment_id"]
        or e["recipient_id"] or e["quote_id"] for e in mine["items"]
    )  # fmt: skip
    assert mine_ids <= {e["event_id"] for e in everything["items"]}


def test_audit_pagination_walks_the_whole_log_newest_first(world: World) -> None:
    world.ready_payment()
    seen: list[int] = []
    cursor = None
    while True:
        path = "/audit/events?limit=7" + (f"&cursor={cursor}" if cursor else "")
        page = world.call("GET", path, "admin").json()
        seen += [e["seq"] for e in page["items"]]
        cursor = page["next_cursor"]
        if cursor is None:
            break
    assert seen == sorted(seen, reverse=True)
    assert seen[-1] == 1
    assert len(seen) == len(set(seen))


def test_every_rule_is_listed_with_its_verified_flag_and_source(world: World) -> None:
    body = world.call("GET", "/config/rules", "student").json()
    by_key = {r["key"]: r for r in body["rules"]}
    living = by_key["bangladesh_rules.living_expense_usd_per_month"]
    assert living["verified"] is False
    assert living["badge"] == "NOT_VERIFIED"
    assert living["source_url"]
    assert "Confirm with your AD bank" in living["indicative"]
    assert by_key["engine.quote_ttl_seconds"]["verified"] is True
    assert body["unverified_count"] > 5


def test_an_admin_can_change_a_rule_without_a_code_change_and_it_is_audited(world: World) -> None:
    change = {
        "key": "limits.daily_usd_equivalent", "value": 150000, "verified": True,
        "reason": "judge asked for a higher sandbox cap",
    }  # fmt: skip
    assert world.call("PUT", "/config/rules", "parent", json=change).status_code == 403
    assert world.call("PUT", "/config/rules", "student", json=change).status_code == 403
    response = world.call("PUT", "/config/rules", "admin", json=change)
    assert response.status_code == 200
    assert response.json()["value"] == 150000
    row = world.audit_rows(action="config.changed")[0]
    assert row["actor_id"] == world.ids["admin"]
    assert row["reason_code"] == "limits.daily_usd_equivalent"
    assert "100000" in row["detail"] and "150000" in row["detail"]
    assert "judge asked" in row["detail"]
    rules = {r["key"]: r for r in world.call("GET", "/config/rules").json()["rules"]}
    assert rules["limits.daily_usd_equivalent"]["updated_by"] == world.ids["admin"]


def test_bad_rule_changes_are_rejected(world: World) -> None:
    def put(**body):
        return world.call("PUT", "/config/rules", "admin", json={"reason": "testing", **body})

    assert put(key="engine.quote_ttl_seconds", value="soon").status_code == 422
    assert put(key="limits.daily_usd_equivalent", value=-5).status_code == 422
    assert put(key="no.such.rule", value=1).status_code == 422
    assert put(key="engine.quote_ttl_seconds", value=600, reason="x").status_code == 422
    regulatory = put(
        key="bangladesh_rules.single_ad_branch_rule", value="one branch", verified=True
    )
    assert regulatory.status_code == 200  # it already has a source_url placeholder
    assert json.loads(regulatory.text)["verified"] is True
