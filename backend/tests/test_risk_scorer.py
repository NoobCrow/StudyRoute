"""The risk model: it reads a payment, says why, is checked before use, and can be off."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import numpy as np
import pytest

from app.ai.risk.features import FEATURE_NAMES, FEATURES
from app.ai.risk.scorer import RiskScorer, load_scorer
from tests.helpers import World
from tests.test_bank_review import LARGE, decide, page, request


def write_model(directory: Path, *, tamper: bool = False, inputs: int = FEATURES) -> Path:
    """A tiny model whose logit is the amount percentile, so its answers can be worked out by hand."""
    weights = np.zeros((inputs, 1))
    weights[FEATURE_NAMES.index("amount_percentile"), 0] = 10.0
    body: dict[str, Any] = {
        "model_id": "test-risk",
        "kind": "linear",
        "features": list(FEATURE_NAMES),
        "layers": [{"w": weights.tolist(), "b": [0.0]}],
        "mean": [0.0] * FEATURES,
        "std": [1.0] * FEATURES,
        "quantiles": {"US Dollar": [float(v) for v in np.linspace(0, 10_000, 101)]},
        "score_quantiles": [float(v) for v in np.linspace(0.0, 10.0, 101)],  # logit 0..10
        "bands": {
            "HIGH": {"from_logit": 9.0, "payments": 10, "flagged_share": 0.5},
            "MEDIUM": {"from_logit": 7.0, "payments": 40, "flagged_share": 0.05},
            "LOW": {"from_logit": None, "payments": 1000, "flagged_share": 0.001},
        },
    }
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / "risk.json"
    path.write_text(json.dumps(body), encoding="utf-8")
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    manifest = {"model_id": "test-risk", "files": {"risk.json": "0" * 64 if tamper else digest}}
    (directory / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    return directory


def facts(amount: float) -> dict[str, Any]:
    return {
        "amount": amount, "currency": "US Dollar", "sender_24h": 0, "sender_7d": 0,
        "sender_total": 0, "hours_since_last": 720.0, "pair_count": 0,
    }  # fmt: skip


def test_the_priority_rises_with_the_amount_and_falls_into_bands(tmp_path: Path) -> None:
    scorer = RiskScorer(write_model(tmp_path))
    small, middle, big = (scorer.score(facts(a)) for a in (500.0, 8_000.0, 9_990.0))
    assert small.band == "LOW" and small.percentile < middle.percentile < big.percentile
    assert middle.band == "MEDIUM" and big.band == "HIGH"
    assert scorer.score(facts(50_000.0)).percentile == 100  # beyond anything seen: the top


def test_the_logit_is_what_the_weights_say(tmp_path: Path) -> None:
    scorer = RiskScorer(write_model(tmp_path))
    assert scorer.logit(facts(5_000.0)) == pytest.approx(5.0)  # 10 x the 0.5 percentile


def test_a_changed_model_file_is_refused(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="SHA-256"):
        RiskScorer(write_model(tmp_path, tamper=True))


def test_a_model_for_other_features_is_refused(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="features"):
        RiskScorer(write_model(tmp_path, inputs=FEATURES - 1))


def test_the_scorer_can_be_switched_off_and_missing_files_are_not_fatal() -> None:
    assert load_scorer("off") is None


# ---- inside the review desk ---------------------------------------------------------------------


class ByAmount:
    """Stands in for the trained model: from USD 40,000 up it reads a payment as riskier."""

    population = "first"

    def score(self, facts_: dict[str, Any]) -> Any:
        from app.ai.risk.scorer import Priority

        amount = facts_["amount"]
        percentile, band = (
            (99, "HIGH")
            if amount >= 48_000
            else (96, "MEDIUM")
            if amount >= 40_000
            else (50, "LOW")
        )
        drivers = ("AMOUNT", "PERSON") if band != "LOW" else ()
        return Priority(percentile, band, "stand-in", "0" * 64, "first", drivers)


def test_the_model_decides_who_a_person_looks_at_and_the_queue_follows_its_reading(
    world: World,
) -> None:
    world.ctx.reviews._scorer = ByAmount()
    medium = request(world, LARGE)["payment_id"]  # about USD 41,967
    high = request(world, {"amount_minor": 3_800_000, "currency": "GBP"})["payment_id"]  # 49,837
    items = world.call("GET", "/bank-review/queue", "admin").json()["items"]
    assert [i["payment_id"] for i in items] == [high, medium]  # the higher reading first
    assert items[0]["priority"]["band"] == "HIGH" and items[1]["priority"]["band"] == "MEDIUM"
    view = world.call("GET", f"/payments/{high}/bank-review", "admin").json()
    assert view["routing"] == "ai" and view["ai"]["band"] == "HIGH"
    assert view["signals"][0]["code"] == "AI_RISK" and view["signals"][0]["needs_human"] is True


def test_the_plain_rules_become_context_when_the_model_is_loaded(world: World) -> None:
    world.ctx.reviews._scorer = ByAmount()
    pid = request(world, LARGE)["payment_id"]
    signals = {s["code"]: s["needs_human"] for s in page(world, pid, "admin")["signals"]}
    assert signals["AI_RISK"] is True
    assert signals["LARGE_AMOUNT"] is False  # still shown, no longer what decides


def test_a_low_reading_takes_the_fast_lane_even_for_a_large_payment(world: World) -> None:
    """The model decides, so a payment it reads as ordinary waits for nobody. A person (the parent)
    still approves it with MFA, and the sandbox caps still apply."""

    class Calm(ByAmount):
        def score(self, facts_: dict[str, Any]) -> Any:
            from app.ai.risk.scorer import Priority

            return Priority(40, "LOW", "stand-in", "0" * 64, "first", ())

    world.ctx.reviews._scorer = Calm()
    approval = request(world, LARGE)
    assert page(world, approval["payment_id"])["status"] == "CLEARED_AUTO"
    assert world.approve(approval).status_code == 200


def test_a_name_list_match_still_goes_to_a_person_whatever_the_model_says(world: World) -> None:
    from tests.test_bank_review import FLAGGED_NAME

    class Calm(ByAmount):
        def score(self, facts_: dict[str, Any]) -> Any:
            from app.ai.risk.scorer import Priority

            return Priority(10, "LOW", "stand-in", "0" * 64, "first", ())

    world.ctx.reviews._scorer = Calm()
    rid = world.call("POST", "/recipients", json=FLAGGED_NAME).json()["recipient_id"]
    world.verify_kyc()
    world.allowlist(rid)
    draft = world.draft(world.quote(), recipient_id=rid)
    world.call("POST", f"/payments/{draft['payment_id']}/request-approval", idem=True)
    view = page(world, draft["payment_id"])
    assert view["status"] == "OPEN" and view["signals"][0]["code"] == "NAME_CHECK"


def test_the_parents_page_gives_the_models_reasons_in_plain_words(world: World) -> None:
    world.ctx.reviews._scorer = ByAmount()
    view = page(world, request(world, LARGE)["payment_id"])
    assert view["ai"]["among"] == "a first payment to this receiver"
    assert [d["code"] for d in view["ai"]["drivers"]] == ["AMOUNT", "PERSON"]
    assert (
        view["ai"]["drivers"][1]["plain"] == "You have not paid this person or university before."
    )
    levels = {f["code"]: f["level"] for f in view["ai"]["factors"]}
    assert list(levels) == [
        "AMOUNT",
        "FREQUENCY",
        "TIMELINE",
        "PERSON",
    ]  # all four are always shown
    assert levels == {
        "AMOUNT": "raises",
        "FREQUENCY": "neutral",
        "TIMELINE": "neutral",
        "PERSON": "raises",
    }
    assert "a computer model" in view["signals"][0]["means"].lower()


def test_the_reading_is_written_to_the_audit_log_with_the_models_name(world: World) -> None:
    world.ctx.reviews._scorer = ByAmount()
    request(world, LARGE)
    rows = world.audit_rows(action="bank_review.opened")
    assert rows[0]["model_version"] == "stand-in"
    assert "routing=ai" in rows[0]["detail"] and "risk=MEDIUM:96" in rows[0]["detail"]


def test_without_the_model_the_plain_rules_decide(world: World) -> None:
    assert world.ctx.reviews._scorer is None
    pid = request(world, LARGE)["payment_id"]
    view = page(world, pid, "admin")
    assert view["routing"] == "rules" and view["ai"] is None
    assert view["signals"][0]["code"] == "LARGE_AMOUNT" and view["signals"][0]["needs_human"]


def test_the_model_names_what_pushed_the_score_up(tmp_path: Path) -> None:
    scorer = RiskScorer(write_model(tmp_path))
    assert scorer.score(facts(9_990.0)).drivers == ("AMOUNT",)
    assert scorer.score(facts(100.0)).drivers == ()  # nothing pushed it up


def test_a_band_comes_with_what_it_meant_in_the_practice_data(tmp_path: Path) -> None:
    scorer = RiskScorer(write_model(tmp_path))
    high, medium, low = (scorer.score(facts(a)) for a in (9_990.0, 8_000.0, 500.0))
    assert (high.band, medium.band, low.band) == ("HIGH", "MEDIUM", "LOW")
    assert (high.hit_rate, medium.hit_rate, low.hit_rate) == (0.5, 0.05, 0.001)
    assert high.to_dict()["hit_rate"] == 0.5
    assert scorer.score({**facts(500.0), "pair_count": 3}).population == "repeat"


# ---- the score, the warning and the authorization ---------------------------------------------------


class Fixed:
    """Stands in for the model with a chosen band."""

    def __init__(self, percentile: int, band: str) -> None:
        self._reading = (percentile, band)

    def score(self, facts_: dict[str, Any]) -> Any:
        from app.ai.risk.scorer import Priority

        percentile, band = self._reading
        factors = (("AMOUNT", 0.1), ("FREQUENCY", -0.5), ("TIMELINE", 1.2), ("PERSON", 0.0))
        drivers = ("TIMELINE",) if band != "LOW" else ()
        return Priority(percentile, band, "stand-in", "0" * 64, "first", drivers, 0.01, factors)


def test_every_payment_has_a_score_and_four_factors_but_only_a_high_one_has_a_warning(
    world: World,
) -> None:
    world.ctx.reviews._scorer = Fixed(12, "LOW")
    low = page(world, request(world)["payment_id"])["ai"]
    assert low["score"] == 12 and low["warning"] is False
    assert [f["title"] for f in low["factors"]] == ["Amount", "Frequency", "Timeline", "Person"]
    assert {f["code"]: f["level"] for f in low["factors"]} == {
        "AMOUNT": "neutral", "FREQUENCY": "lowers", "TIMELINE": "raises", "PERSON": "neutral",
    }  # fmt: skip
    assert low["drivers"] == []  # nothing is named as a reason when the score is low
    world.ctx.reviews._scorer = Fixed(99, "HIGH")
    high = page(world, request(world, LARGE)["payment_id"])["ai"]
    assert high["score"] == 99 and high["warning"] is True
    assert [d["code"] for d in high["drivers"]] == ["TIMELINE"]


def test_every_payment_needs_the_parents_mfa_authorization_whatever_its_score(
    world: World,
) -> None:
    world.ctx.reviews._scorer = Fixed(5, "LOW")
    approval = request(world)
    assert page(world, approval["payment_id"])["status"] == "CLEARED_AUTO"  # no warning, no wait
    without = world.call(
        "POST",
        f"/payments/{approval['payment_id']}/approve",
        json={"confirm_summary_hash": approval["summary_hash"]},
        idem=True,
    )
    assert without.status_code == 403 and without.json()["code"] == "MFA_REQUIRED"
    assert world.approve(approval).status_code == 200  # authorized: only now does it go through


def test_a_high_score_warns_and_still_needs_the_same_authorization(world: World) -> None:
    world.ctx.reviews._scorer = Fixed(99, "HIGH")
    approval = request(world, LARGE)
    pid = approval["payment_id"]
    assert page(world, pid)["ai"]["warning"] is True
    assert world.approve(approval).status_code == 409  # the bank has not said yes yet
    assert decide(world, pid, "CLEAR").status_code == 200
    assert world.approve(approval).status_code == 200  # then the parent's MFA authorizes it


def test_the_bank_can_be_set_to_authorize_every_payment_low_score_or_high(world: World) -> None:
    change = {
        "key": "review.bank_authorizes_every_payment",
        "value": True,
        "verified": True,
        "reason": "the bank authorizes every payment",
    }
    assert world.call("PUT", "/config/rules", "admin", json=change).status_code == 200
    world.ctx.reviews._scorer = Fixed(5, "LOW")
    approval = request(world)
    pid = approval["payment_id"]
    view = page(world, pid)
    assert view["status"] == "OPEN" and view["ai"]["warning"] is False  # waits, but no warning
    assert view["signals"][0]["code"] == "BANK_AUTHORIZES_ALL"
    assert world.approve(approval).status_code == 409
    assert decide(world, pid, "CLEAR").status_code == 200
    assert world.approve(approval).status_code == 200
