"""The provider simulator: approval -> submit -> signed webhook -> settled / failed."""

from __future__ import annotations

from typing import Any

from sqlalchemy import select

from app.engine.validators import is_valid_uetr
from app.models import ProviderLedger
from app.worker import BackgroundWorker
from tests.helpers import World


def state(world: World, pid: str) -> str:
    return str(world.call("GET", f"/payments/{pid}").json()["state"])


def approved(world: World, recipient: str | None = None) -> dict[str, Any]:
    world.verify_kyc()
    rid = world.recipient_id(recipient) if recipient else world.recipient_id()
    world.allowlist(rid)
    payment = world.draft(recipient_id=rid)
    approval = world.call("POST", f"/payments/{payment['payment_id']}/request-approval", idem=True)
    assert approval.status_code == 200, approval.text
    assert world.approve(approval.json()).status_code == 200
    return {"payment_id": payment["payment_id"]}


def test_normal_flow_submits_after_three_seconds_and_settles_after_five_more(world: World) -> None:
    pid = approved(world)["payment_id"]
    world.clock.advance(2)
    assert world.ctx.worker.tick()["payments_submitted"] == 0
    assert state(world, pid) == "APPROVED"
    world.clock.advance(1)
    assert world.ctx.worker.tick()["payments_submitted"] == 1
    detail = world.call("GET", f"/payments/{pid}").json()
    assert detail["state"] == "SUBMITTED"
    assert is_valid_uetr(detail["uetr"])
    world.clock.advance(4)
    assert world.ctx.worker.tick()["webhooks_delivered"] == 0
    world.clock.advance(1)
    assert world.ctx.worker.tick()["webhooks_delivered"] == 1
    assert state(world, pid) == "SETTLED"
    body, headers = world.dispatcher.sent[0]
    assert headers["X-Signature"].startswith("t=")
    assert b'"simulated":true' in body


def test_cancelling_inside_the_window_stops_the_submission(world: World) -> None:
    pid = approved(world)["payment_id"]
    world.clock.advance(1)
    assert world.call("POST", f"/payments/{pid}/cancel", idem=True).status_code == 200
    world.clock.advance(60)
    result = world.ctx.worker.tick()
    assert result["payments_submitted"] == 0
    assert state(world, pid) == "CANCELLED"
    with world.ctx.db.read() as session:
        assert session.execute(select(ProviderLedger)).first() is None


def test_a_fail_test_recipient_ends_in_failed(world: World) -> None:
    pid = approved(world, "FAIL_TEST University (synthetic)")["payment_id"]
    world.clock.advance(3)
    world.ctx.worker.tick()
    world.clock.advance(5)
    world.ctx.worker.tick()
    detail = world.call("GET", f"/payments/{pid}").json()
    assert detail["state"] == "FAILED"
    assert "simulated" in detail["failure_reason"]


def test_a_slow_test_recipient_settles_after_thirty_seconds(world: World) -> None:
    created = world.call(
        "POST", "/recipients",
        json={"type": "UNIVERSITY", "display_name": "SLOW_TEST College (synthetic)",
              "country": "GB", "bic": "EXMPGB2L", "iban": "GB13EXMP12345600005555"},
    )  # fmt: skip
    assert created.status_code == 201
    pid = approved(world, "SLOW_TEST College (synthetic)")["payment_id"]
    world.clock.advance(3)
    world.ctx.worker.tick()
    world.clock.advance(10)
    world.ctx.worker.tick()
    assert state(world, pid) == "SUBMITTED"
    world.clock.advance(20)
    world.ctx.worker.tick()
    assert state(world, pid) == "SETTLED"


def test_a_failing_delivery_is_retried_and_the_state_survives_a_restart(world: World) -> None:
    pid = approved(world)["payment_id"]
    world.clock.advance(3)
    world.ctx.worker.tick()
    real = world.dispatcher.client
    world.dispatcher.client = None  # simulate the API being unreachable

    class Down:
        def post(self, body: bytes, headers: Any) -> int:
            return 503

    world.ctx.simulator._dispatcher = Down()  # type: ignore[assignment]  # noqa: SLF001
    world.clock.advance(5)
    world.ctx.worker.tick()
    assert state(world, pid) == "SUBMITTED"
    world.dispatcher.client = real
    world.ctx.simulator._dispatcher = world.dispatcher  # noqa: SLF001
    world.clock.advance(6)
    BackgroundWorker(world.ctx).tick()  # a "restarted" worker has no memory, only the database
    assert state(world, pid) == "SETTLED"
