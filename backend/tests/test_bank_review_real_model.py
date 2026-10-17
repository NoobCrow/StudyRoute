"""The review desk with the real, shipped risk model (skipped when its files are not there).

The stand-in model tests in test_risk_scorer.py prove the arrangement; these prove that the model that
ships does what the documents say: an ordinary payment takes the fast lane, and a run of quick payments
followed by a first payment to a new receiver is read as unusual and waits for a person.
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest

from app.ai.risk.scorer import MODEL_DIR
from tests.helpers import World
from tests.test_bank_review import FLAGGED_NAME, decide, page

if not (MODEL_DIR / "risk.json").exists():  # pragma: no cover - a stripped checkout
    pytest.skip("the shipped risk model is not available", allow_module_level=True)

UNIVERSITY_2 = {**FLAGGED_NAME, "display_name": "Second University of Example (synthetic)"}


@pytest.fixture
def real(tmp_path: Path) -> Iterator[World]:
    world = World(tmp_path, risk_mode="auto")
    assert world.ctx.reviews._scorer is not None
    world.verify_kyc()
    world.allowlist()
    yield world
    world.close()


def pay(world: World, amount_minor: int, recipient_id: str | None = None) -> str:
    quote = world.quote(target={"amount_minor": amount_minor, "currency": "GBP"})
    draft = world.draft(quote, **({"recipient_id": recipient_id} if recipient_id else {}))
    pid = str(draft["payment_id"])
    assert world.call("POST", f"/payments/{pid}/request-approval", idem=True).status_code == 200
    return pid


def busy_run_then_new_receiver(world: World) -> tuple[str, dict[str, Any]]:
    for _ in range(5):
        pay(world, 500_000)
        world.clock.advance(300)
    rid = world.call("POST", "/recipients", json=UNIVERSITY_2).json()["recipient_id"]
    world.allowlist(rid)
    pid = pay(world, 1_500_000, rid)
    return pid, page(world, pid)


def test_an_ordinary_first_payment_is_read_as_lower_risk_and_waits_for_nobody(real: World) -> None:
    view = page(real, pay(real, 1_000_000))
    assert view["status"] == "CLEARED_AUTO" and view["ai"]["band"] == "LOW"
    assert view["ai"]["drivers"] == []  # reasons are named only when the rating is not low
    assert "No bank check needed" in view["headline"]


def test_a_run_of_quick_payments_then_a_new_receiver_is_read_as_unusual_and_waits(
    real: World,
) -> None:
    _, view = busy_run_then_new_receiver(real)
    assert view["status"] == "OPEN" and view["lane"] == "reviewed"
    assert view["ai"]["band"] in ("MEDIUM", "HIGH")
    assert {d["code"] for d in view["ai"]["drivers"]} >= {"PERSON"}
    assert view["signals"][0]["code"] == "AI_RISK"
    assert view["ai"]["hit_rate"] > 0.01  # what that band meant in the tuning data


def test_the_reviewer_sees_the_models_reading_and_the_audit_log_names_the_model(
    real: World,
) -> None:
    pid, _ = busy_run_then_new_receiver(real)
    brief = page(real, pid, "admin")
    assert brief["routing"] == "ai" and brief["ai"]["model_id"] == "studyroute-risk-v1"
    opened = real.audit_rows(action="bank_review.opened")
    assert opened and opened[-1]["model_version"] == "studyroute-risk-v1"
    assert "routing=ai" in opened[-1]["detail"]


def test_a_person_can_still_clear_what_the_model_flagged_and_the_parent_then_approves(
    real: World,
) -> None:
    pid, _ = busy_run_then_new_receiver(real)
    assert decide(real, pid, "CLEAR").status_code == 200
    summary = real.call("GET", f"/payments/{pid}").json()["summary_hash"]
    approval = {"payment_id": pid, "summary_hash": summary}
    assert real.approve(approval).status_code == 200
