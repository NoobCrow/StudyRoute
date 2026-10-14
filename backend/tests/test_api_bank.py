"""The sandbox bank network through the API: national and international transfers end to end."""

from __future__ import annotations

import uuid
from collections import Counter
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import update

from app.core.secret_store import _generate_aes_key, _generate_ec_pem, _generate_hex_secret
from app.models import BankAccount
from tests.helpers import World

PARENT_A, PARENT_B, PARENT_C = "SBX-A-0001", "SBX-B-0001", "SBX-C-0001"
COUSIN_A, RELATIVE_B = "SBX-A-0002", "SBX-B-0002"
STUDENT_GBP, LANDLORD, SLOW_LANDLORD = "SBX-X-0001", "SBX-X-0002", "SBX-X-0003"
UNIVERSITY = "GB08EXMP12345612344821"
FAIL_UNIVERSITY = "GB13EXMP12345600005555"
SANCTIONED = "SBX-L-0099"
TERMINAL = {"SETTLED", "RETURNED", "CANCELLED"}


@pytest.fixture
def world(tmp_path: Path) -> Iterator[World]:
    instance = World(tmp_path, bank_network=True)
    yield instance
    instance.close()


def accounts(world: World, who: str = "parent") -> dict[str, dict[str, Any]]:
    items = world.call("GET", "/bank/accounts", who).json()["items"]
    return {a["number"]: a for a in items}


def balance(world: World, number: str) -> int:
    """Any customer account's balance, read through the admin view."""
    items = world.call("GET", "/bank/accounts", "admin").json()["items"]
    return int(next(a for a in items if a["number"] == number)["balance"]["amount_minor"])


def plan(
    world: World, source: str, dest: str, amount: int, currency: str, **extra: Any
) -> dict[str, Any]:
    body = {
        "source": source,
        "destination": dest,
        "amount": {"amount_minor": amount, "currency": currency},
        **extra,
    }
    response = world.call("POST", "/bank/transfers", json=body, idem=True)
    assert response.status_code == 201, response.text
    return dict(response.json())


def confirm(world: World, transfer_id: str) -> Any:
    proof = world.mfa("parent", "confirm_bank_transfer", transfer_id)
    return world.call("POST", f"/bank/transfers/{transfer_id}/confirm", idem=True, mfa=proof)


def settle(world: World, transfer_id: str, seconds: int = 30, limit: int = 12) -> dict[str, Any]:
    """Advance the clock and run the worker until the transfer stops moving."""
    view: dict[str, Any] = {}
    for _ in range(limit):
        world.clock.advance(seconds)
        world.ctx.worker.tick()
        view = world.call("GET", f"/bank/transfers/{transfer_id}", "parent").json()
        if view["status"] in TERMINAL:
            return view
    return view


def send(
    world: World, source: str, dest: str, amount: int, currency: str, **extra: Any
) -> dict[str, Any]:
    created = plan(world, source, dest, amount, currency, **extra)
    reply = confirm(world, created["id"])
    assert reply.status_code == 200, reply.text
    return settle(world, created["id"])


def overview(world: World) -> dict[str, Any]:
    return dict(world.call("GET", "/bank/network", "admin").json())


def actions(world: World) -> list[str]:
    rows = world.call("GET", "/audit/events?limit=100", "admin").json()["items"]
    return [r["action"] for r in rows if r["action"].startswith("bank.")]


# --- the network and who can see it ----------------------------------------------------------


def test_the_network_is_ready_balanced_and_all_synthetic(world: World) -> None:
    body = overview(world)
    assert body["ready"] and body["simulated"] and body["all_ok"]
    codes = {b["code"] for b in body["directory"]["banks"]}
    assert {"EXMPBDA1", "EXMPBDB1", "EXMPBDC1", "EXMPGB2L", "EXMPUS6C"} <= codes
    assert all(code.startswith("EXMP") for code in codes)
    assert all(t["balanced"] for t in body["trial_balance"].values())


def test_each_role_sees_the_right_accounts(world: World) -> None:
    parent = accounts(world, "parent")
    assert set(parent) == {PARENT_A, PARENT_B, PARENT_C, STUDENT_GBP}
    assert parent[PARENT_A]["balance"]["amount_minor"] == 500_000_000
    assert set(accounts(world, "student")) == set(parent)
    everything = accounts(world, "admin")
    assert UNIVERSITY in everything and len(everything) > len(parent)


def test_beneficiaries_list_every_customer_without_balances(world: World) -> None:
    items = world.call("GET", "/bank/beneficiaries", "parent").json()["items"]
    assert UNIVERSITY in {i["number"] for i in items}
    assert all("balance" not in i for i in items)


def test_the_ai_has_no_bank_access(world: World) -> None:
    reply = world.client.get("/api/v1/bank/accounts", headers=world.ai_headers())
    assert (reply.status_code, reply.json()["code"]) == (403, "FORBIDDEN")


def test_only_the_parent_can_plan_a_transfer(world: World) -> None:
    body = {
        "source": PARENT_A,
        "destination": RELATIVE_B,
        "amount": {"amount_minor": 100_000, "currency": "BDT"},
    }
    for who in ("student", "admin"):
        reply = world.call("POST", "/bank/transfers", who, json=body, idem=True)
        assert reply.status_code == 403, who


def test_production_mode_has_no_bank_surface(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("JWT_PRIVATE_KEY_PEM", _generate_ec_pem().replace("\n", chr(92) + "n"))
    monkeypatch.setenv("DATA_ENCRYPTION_KEY", _generate_aes_key())
    for provider in ("PROV_A", "PROV_B", "PROV_C"):
        monkeypatch.setenv(f"WEBHOOK_SECRET_{provider}", _generate_hex_secret())
    prod = World(tmp_path, app_env="production")
    try:
        assert prod.client.get("/api/v1/bank/network").status_code in (401, 404)
        assert prod.client.get("/api/v1/bank/accounts").status_code in (401, 404)
    finally:
        prod.close()


# --- national transfers ----------------------------------------------------------------------


def test_a_same_bank_transfer_is_free_and_nearly_instant(world: World) -> None:
    before = balance(world, PARENT_A)
    view = send(world, PARENT_A, COUSIN_A, 250_000, "BDT")
    assert view["status"] == "SETTLED" and view["rail"] == "ON_US"
    assert view["fee"]["amount_minor"] == 0
    assert balance(world, PARENT_A) == before - 250_000
    assert balance(world, COUSIN_A) == 1_500_000 + 250_000


def test_an_instant_interbank_transfer_charges_the_fee_and_credits_the_receiver(
    world: World,
) -> None:
    before_a, before_b = balance(world, PARENT_A), balance(world, RELATIVE_B)
    view = send(world, PARENT_A, RELATIVE_B, 100_000, "BDT", rail="INSTANT")
    assert view["status"] == "SETTLED" and view["fee"]["amount_minor"] == 500
    assert balance(world, PARENT_A) == before_a - 100_500
    assert balance(world, RELATIVE_B) == before_b + 100_000
    assert [s["stage"] for s in view["steps"]] == ["SENDING_BANK", "CLEARING", "RECEIVING_BANK"]
    assert overview(world)["all_ok"]


def test_the_batch_rail_waits_for_its_window(world: World) -> None:
    created = plan(world, PARENT_A, RELATIVE_B, 100_000, "BDT", rail="BATCH")
    assert confirm(world, created["id"]).status_code == 200
    world.clock.advance(10)
    world.ctx.worker.tick()
    assert world.call("GET", f"/bank/transfers/{created['id']}").json()["status"] == "ACCEPTED"
    world.clock.advance(11)
    world.ctx.worker.tick()
    assert world.call("GET", f"/bank/transfers/{created['id']}").json()["status"] == "IN_TRANSIT"
    assert settle(world, created["id"])["status"] == "SETTLED"


def test_the_cheapest_rail_is_chosen_when_none_is_named(world: World) -> None:
    created = plan(world, PARENT_A, RELATIVE_B, 100_000, "BDT")
    assert created["rail"] == "BATCH" and created["fee"]["amount_minor"] == 200


def test_rail_limits_are_refused_with_a_reason(world: World) -> None:
    body = {
        "source": PARENT_A,
        "destination": RELATIVE_B,
        "amount": {"amount_minor": 100_000, "currency": "BDT"},
        "rail": "HIGH_VALUE",
    }
    reply = world.call("POST", "/bank/transfers", json=body, idem=True)
    assert reply.status_code == 422 and reply.json()["reason"] == "BELOW_RAIL_MINIMUM"


def test_a_uk_transfer_runs_over_the_uk_clearing_house(world: World) -> None:
    before = balance(world, STUDENT_GBP)
    view = send(world, STUDENT_GBP, UNIVERSITY, 20_000, "GBP", rail="INSTANT")
    assert view["status"] == "SETTLED" and view["fee"]["amount_minor"] == 0
    assert balance(world, STUDENT_GBP) == before - 20_000
    assert overview(world)["all_ok"]


def test_slow_test_stretches_every_delay(world: World) -> None:
    created = plan(world, STUDENT_GBP, SLOW_LANDLORD, 1_000, "GBP")
    assert created["rail"] == "ON_US"
    assert confirm(world, created["id"]).status_code == 200
    world.clock.advance(3)
    world.ctx.worker.tick()
    assert world.call("GET", f"/bank/transfers/{created['id']}").json()["status"] == "ACCEPTED"
    world.clock.advance(4)
    world.ctx.worker.tick()
    assert world.call("GET", f"/bank/transfers/{created['id']}").json()["status"] == "SETTLED"


def test_unsupported_routes_are_refused(world: World) -> None:
    inbound = {
        "source": STUDENT_GBP,
        "destination": PARENT_A,
        "amount": {"amount_minor": 1_000, "currency": "GBP"},
    }
    reply = world.call("POST", "/bank/transfers", json=inbound, idem=True)
    assert (reply.status_code, reply.json()["code"]) == (422, "ROUTE_NOT_SUPPORTED")
    wrong_currency = {
        "source": PARENT_A,
        "destination": UNIVERSITY,
        "amount": {"amount_minor": 1_000_00, "currency": "USD"},
    }
    reply = world.call("POST", "/bank/transfers", json=wrong_currency, idem=True)
    assert reply.status_code == 422


def test_an_account_outside_the_household_cannot_be_the_source(world: World) -> None:
    body = {
        "source": UNIVERSITY,
        "destination": PARENT_A,
        "amount": {"amount_minor": 1_000, "currency": "GBP"},
    }
    assert world.call("POST", "/bank/transfers", json=body, idem=True).status_code == 404


# --- international transfers -----------------------------------------------------------------


def quote_row(world: World, provider: str, code: str, major: int = 10_000) -> dict[str, Any]:
    quote = world.quote(target={"amount_minor": major * 100, "currency": "GBP"}, charge_code=code)
    return next(r for r in quote["results"] if r["provider_id"] == provider)


def test_an_international_transfer_needs_verified_kyc(world: World) -> None:
    created = plan(world, PARENT_A, UNIVERSITY, 1_000_000, "GBP", charge_code="OUR")
    assert [b["code"] for b in created["blockers"]] == ["KYC_NOT_VERIFIED"]
    reply = confirm(world, created["id"])
    assert (reply.status_code, reply.json()["code"]) == (422, "KYC_NOT_VERIFIED")
    assert balance(world, PARENT_A) == 500_000_000


@pytest.mark.parametrize(
    ("source", "provider"), [(PARENT_A, "prov_a"), (PARENT_B, "prov_b"), (PARENT_C, "prov_c")]
)
@pytest.mark.parametrize("code", ["OUR", "SHA", "BEN"])
def test_international_numbers_equal_the_compare_screen(
    world: World, source: str, provider: str, code: str
) -> None:
    world.verify_kyc()
    row = quote_row(world, provider, code)
    before_source, before_dest = balance(world, source), balance(world, UNIVERSITY)
    view = send(world, source, UNIVERSITY, 1_000_000, "GBP", charge_code=code)
    assert view["status"] == "SETTLED", view
    assert view["debit"]["amount_minor"] == row["parent_pays_bdt_minor"]
    assert view["credit"]["amount_minor"] == row["beneficiary_receives_minor"]
    assert balance(world, source) == before_source - row["parent_pays_bdt_minor"]
    assert balance(world, UNIVERSITY) == before_dest + row["beneficiary_receives_minor"]
    assert [s["stage"] for s in view["steps"]] == [
        "ORIGINATING_BANK",
        "CORRESPONDENT",
        "BENEFICIARY_BANK",
    ]
    assert all(s["done"] for s in view["steps"])
    assert overview(world)["all_ok"]


def test_our_delivers_the_full_invoice_amount(world: World) -> None:
    world.verify_kyc()
    before = balance(world, UNIVERSITY)
    view = send(world, PARENT_B, UNIVERSITY, 1_000_000, "GBP", charge_code="OUR")
    assert view["credit"]["amount_minor"] == 1_000_000
    assert balance(world, UNIVERSITY) == before + 1_000_000


def test_the_mt103_hops_carry_the_uetr_and_a_masked_beneficiary(world: World) -> None:
    world.verify_kyc()
    view = send(world, PARENT_A, UNIVERSITY, 1_000_000, "GBP", charge_code="SHA")
    detail = world.call("GET", f"/bank/transfers/{view['id']}").json()
    messages = [e["message"] for e in detail["events"] if e["message"]]
    assert [m["type"] for m in messages] == ["MT103", "MT103", "CREDIT_ADVICE"]
    fields = {f["tag"]: f["value"] for f in messages[0]["fields"]}
    assert fields[":71A:"] == "SHA" and detail["uetr"] in fields["{121:}"]
    assert UNIVERSITY not in str(messages)
    assert "GB** **** 4821" in fields[":59:"]
    assert all(m["simulated"] for m in messages)


def test_international_amounts_above_the_sandbox_cap_are_refused(world: World) -> None:
    body = {
        "source": PARENT_A,
        "destination": UNIVERSITY,
        "amount": {"amount_minor": 4_000_000, "currency": "GBP"},
    }
    reply = world.call("POST", "/bank/transfers", json=body, idem=True)
    assert (reply.status_code, reply.json()["code"]) == (422, "LIMIT_EXCEEDED")


# --- failures and screening ------------------------------------------------------------------


def test_a_rejecting_beneficiary_bank_returns_every_taka_and_every_fee(world: World) -> None:
    world.verify_kyc()
    snapshot = {n: balance(world, n) for n in (PARENT_B, FAIL_UNIVERSITY)}
    view = send(world, PARENT_B, FAIL_UNIVERSITY, 1_000_000, "GBP", charge_code="OUR")
    assert view["status"] == "RETURNED"
    assert "returned in full" in view["events"][-1]["note"]
    assert {n: balance(world, n) for n in snapshot} == snapshot
    assert all(not s["done"] for s in view["steps"])
    body = overview(world)
    assert body["all_ok"]
    assert "bank.transfer_returned" in actions(world)


def test_a_domestic_failure_is_also_unwound(world: World) -> None:
    before = balance(world, PARENT_A)
    created = plan(world, PARENT_A, RELATIVE_B, 100_000, "BDT", rail="INSTANT")
    assert confirm(world, created["id"]).status_code == 200
    world.clock.advance(5)
    world.ctx.worker.tick()  # the sending bank has released the money
    mid = world.call("GET", f"/bank/transfers/{created['id']}").json()
    assert mid["status"] == "IN_TRANSIT" and balance(world, PARENT_A) == before - 100_500
    stopped = world.call(
        "POST", f"/bank/transfers/{created['id']}/sandbox-step", "admin", json={"outcome": "fail"}
    )
    assert stopped.status_code == 200 and stopped.json()["status"] == "RETURNED"
    assert balance(world, PARENT_A) == before
    assert overview(world)["all_ok"]


def test_sanctions_screening_blocks_before_any_money_moves(world: World) -> None:
    world.verify_kyc()
    body = {
        "source": PARENT_A,
        "destination": SANCTIONED,
        "amount": {"amount_minor": 1_000_000, "currency": "GBP"},
    }
    reply = world.call("POST", "/bank/transfers", json=body, idem=True)
    assert (reply.status_code, reply.json()["code"]) == (422, "SANCTIONS_HIT")
    assert "bank.transfer_blocked" in actions(world)
    assert world.call("GET", "/bank/transfers").json()["items"] == []


def test_insufficient_funds_stops_the_confirmation_and_changes_nothing(world: World) -> None:
    created = plan(world, STUDENT_GBP, LANDLORD, 90_000, "GBP")
    assert [b["code"] for b in created["blockers"]] == ["INSUFFICIENT_FUNDS"]
    reply = confirm(world, created["id"])
    assert (reply.status_code, reply.json()["code"]) == (422, "INSUFFICIENT_FUNDS")
    assert balance(world, STUDENT_GBP) == 80_000
    state = world.call("GET", f"/bank/transfers/{created['id']}").json()["status"]
    assert state == "PENDING_CONFIRMATION"


# --- confirmation, MFA, idempotency ----------------------------------------------------------


def test_confirming_needs_a_proof_for_that_exact_transfer(world: World) -> None:
    first = plan(world, PARENT_A, COUSIN_A, 100_000, "BDT")
    second = plan(world, PARENT_A, COUSIN_A, 200_000, "BDT")
    path = f"/bank/transfers/{first['id']}/confirm"
    none = world.call("POST", path, idem=True)
    assert (none.status_code, none.json()["code"]) == (403, "MFA_REQUIRED")
    other = world.mfa("parent", "confirm_bank_transfer", second["id"])
    wrong = world.call("POST", path, idem=True, mfa=other)
    assert (wrong.status_code, wrong.json()["code"]) == (403, "MFA_REQUIRED")
    payment_proof = world.mfa("parent", "allowlist_recipient", world.recipient_id())
    assert world.call("POST", path, idem=True, mfa=payment_proof).status_code == 403
    assert balance(world, PARENT_A) == 500_000_000


def test_an_mfa_proof_works_once(world: World) -> None:
    first = plan(world, PARENT_A, COUSIN_A, 100_000, "BDT")
    proof = world.mfa("parent", "confirm_bank_transfer", first["id"])
    path = f"/bank/transfers/{first['id']}/confirm"
    assert world.call("POST", path, idem=True, mfa=proof).status_code == 200
    again = world.call("POST", path, idem=True, mfa=proof)
    assert again.status_code == 409


def test_a_retried_confirmation_with_the_same_key_replays_the_answer(world: World) -> None:
    created = plan(world, PARENT_A, COUSIN_A, 100_000, "BDT")
    proof = world.mfa("parent", "confirm_bank_transfer", created["id"])
    key = str(uuid.uuid4())
    path = f"/bank/transfers/{created['id']}/confirm"
    first = world.call("POST", path, idem=key, mfa=proof)
    second = world.call("POST", path, idem=key, mfa=proof)
    assert first.status_code == second.status_code == 200
    assert first.json() == second.json()
    assert balance(world, PARENT_A) == 500_000_000 - 100_000


def test_planning_needs_an_idempotency_key_and_repeats_replay(world: World) -> None:
    body = {
        "source": PARENT_A,
        "destination": COUSIN_A,
        "amount": {"amount_minor": 1_000, "currency": "BDT"},
    }
    assert world.call("POST", "/bank/transfers", json=body).status_code == 400
    key = str(uuid.uuid4())
    one = world.call("POST", "/bank/transfers", json=body, idem=key)
    two = world.call("POST", "/bank/transfers", json=body, idem=key)
    assert one.json()["id"] == two.json()["id"]
    assert len(world.call("GET", "/bank/transfers").json()["items"]) == 1
    changed = {**body, "amount": {"amount_minor": 2_000, "currency": "BDT"}}
    assert world.call("POST", "/bank/transfers", json=changed, idem=key).status_code == 422


def test_a_pending_transfer_can_be_cancelled_but_a_confirmed_one_cannot(world: World) -> None:
    pending = plan(world, PARENT_A, COUSIN_A, 100_000, "BDT")
    cancelled = world.call("POST", f"/bank/transfers/{pending['id']}/cancel", idem=True)
    assert cancelled.status_code == 200 and cancelled.json()["status"] == "CANCELLED"
    live = plan(world, PARENT_A, COUSIN_A, 100_000, "BDT")
    assert confirm(world, live["id"]).status_code == 200
    late = world.call("POST", f"/bank/transfers/{live['id']}/cancel", idem=True)
    assert late.status_code == 409


# --- audit, control and integrity ------------------------------------------------------------


def test_every_state_change_is_in_the_audit_log_and_the_chain_verifies(world: World) -> None:
    world.verify_kyc()
    send(world, PARENT_A, UNIVERSITY, 1_000_000, "GBP", charge_code="OUR")
    assert Counter(actions(world)) == {
        "bank.transfer_created": 1,
        "bank.transfer_confirmed": 1,
        "bank.transfer_step": 2,
        "bank.transfer_settled": 1,
    }
    verify = world.call("GET", "/audit/verify", "admin").json()
    assert verify["status"] == "PASS"


def test_only_the_reviewer_can_move_a_transfer_by_hand(world: World) -> None:
    created = plan(world, PARENT_A, COUSIN_A, 100_000, "BDT")
    assert confirm(world, created["id"]).status_code == 200
    path = f"/bank/transfers/{created['id']}/sandbox-step"
    assert world.call("POST", path, "parent", json={"outcome": "advance"}).status_code == 403
    moved = world.call("POST", path, "admin", json={"outcome": "advance"})
    assert moved.status_code == 200 and moved.json()["status"] == "SETTLED"


def test_a_statement_shows_entries_with_running_balances(world: World) -> None:
    send(world, PARENT_A, COUSIN_A, 100_000, "BDT")
    account = accounts(world)[PARENT_A]
    body = world.call("GET", f"/bank/accounts/{account['id']}/statement").json()
    assert body["entries"][0]["balance_after_minor"] == 500_000_000 - 100_000
    assert body["entries"][0]["side"] == "DEBIT"
    other = accounts(world, "admin")[UNIVERSITY]
    assert world.call("GET", f"/bank/accounts/{other['id']}/statement").status_code == 404


def test_editing_a_balance_behind_the_ledgers_back_is_detected(world: World) -> None:
    assert overview(world)["all_ok"]
    with world.ctx.db.write() as session:
        session.execute(
            update(BankAccount)
            .where(BankAccount.number == PARENT_A)
            .values(balance_minor=BankAccount.balance_minor + 1)
        )
    body = overview(world)
    assert not body["all_ok"] and body["accounts_not_matching_entries"] == 1


def test_money_in_every_view_is_an_integer(world: World) -> None:
    world.verify_kyc()
    view = send(world, PARENT_A, UNIVERSITY, 1_000_000, "GBP", charge_code="OUR")
    detail = world.call("GET", f"/bank/transfers/{view['id']}").json()
    for money in (detail["debit"], detail["credit"], detail["fee"]):
        assert isinstance(money["amount_minor"], int)
    for journal in detail["journals"]:
        for line in journal["lines"]:
            assert isinstance(line["amount"]["amount_minor"], int)


def test_bank_writes_have_their_own_rate_limit(tmp_path: Path) -> None:
    limited = World(tmp_path, bank_network=True, rate_limit_enabled=True)
    try:
        body = {
            "source": PARENT_A,
            "destination": COUSIN_A,
            "amount": {"amount_minor": 1_000, "currency": "BDT"},
        }
        codes = [
            limited.call("POST", "/bank/transfers", json=body, idem=True).status_code
            for _ in range(22)
        ]
        assert codes[:20] == [201] * 20 and codes[20:] == [429, 429]
    finally:
        limited.close()
