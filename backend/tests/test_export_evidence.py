"""The execution-evidence exporter writes complete, valid and secret-free files."""

from __future__ import annotations

import json
from collections.abc import Iterator
from pathlib import Path

import pytest

from app.scripts.export_evidence import collect_evidence
from tests.helpers import MFA_CODE, PASSWORD, World


@pytest.fixture
def world(tmp_path: Path) -> Iterator[World]:
    """The demo now includes the sandbox bank network, so seed it."""
    instance = World(tmp_path, bank_network=True)
    yield instance
    instance.close()


def export(world: World, out: Path, *, tamper: bool) -> list[str]:
    def wait(seconds: float) -> None:
        world.clock.advance(seconds)
        world.ctx.worker.tick()

    db_file = Path(world.settings.database_url.removeprefix("sqlite:///")) if tamper else None
    return collect_evidence(
        world.client, out, password=PASSWORD, mfa_code=MFA_CODE,
        wait=wait, say=lambda _: None, tamper_db=db_file,
    )  # fmt: skip


def test_the_evidence_files_are_written_and_the_demo_passed(world: World, tmp_path: Path) -> None:
    out = tmp_path / "evidence"
    assert export(world, out, tamper=False) == []
    for name in (
        "sandbox_operation_log.txt",
        "audit_log.json",
        "audit_verify.json",
        "payments.json",
        "bank_network.json",
        "smart_escrow.json",
        "README.md",
    ):
        assert (out / name).is_file(), name
    log = (out / "sandbox_operation_log.txt").read_text("utf-8")
    failed_checks = [line for line in log.splitlines() if line.strip().startswith("FAIL")]
    assert failed_checks == []
    assert log.count("OK  ") >= 25, "every demo check is recorded"
    assert "chain verifies: PASS" in log
    audit = json.loads((out / "audit_log.json").read_text("utf-8"))
    seqs = [e["seq"] for e in audit["events"]]
    assert seqs == sorted(seqs) and audit["count"] == len(seqs) > 10
    assert json.loads((out / "audit_verify.json").read_text("utf-8"))["status"] == "PASS"
    payments = json.loads((out / "payments.json").read_text("utf-8"))
    assert payments[0]["tracker"]["state"] == "SETTLED"
    assert payments[0]["tracker"]["uetr"]
    bank = json.loads((out / "bank_network.json").read_text("utf-8"))
    assert bank["network"]["all_ok"] is True
    statuses = sorted(t["status"] for t in bank["transfers"])
    assert statuses == ["RETURNED", "SETTLED", "SETTLED"]
    assert {t["kind"] for t in bank["transfers"]} == {"NATIONAL", "INTERNATIONAL"}
    assert all(t["journals"] and t["events"] for t in bank["transfers"])
    escrow = json.loads((out / "smart_escrow.json").read_text("utf-8"))
    assert escrow["escrows"] and escrow["anchors"]
    assert escrow["chain"]["integrity"]["ok"] is True
    assert escrow["anchor_check"]["status"] == "PASS"


def test_the_tamper_demo_records_fail_then_pass(world: World, tmp_path: Path) -> None:
    out = tmp_path / "evidence"
    assert export(world, out, tamper=True) == []
    tamper = json.loads((out / "tamper_demo.json").read_text("utf-8"))
    assert tamper["verify_after_edit"]["status"] == "FAIL"
    assert tamper["verify_after_edit"]["failed_seq"] == tamper["edited_event"]["seq"]
    assert tamper["verify_after_restore"]["status"] == "PASS"
    assert json.loads((out / "audit_verify.json").read_text("utf-8"))["status"] == "PASS"


def test_no_secret_ever_reaches_the_evidence_files(world: World, tmp_path: Path) -> None:
    out = tmp_path / "evidence"
    export(world, out, tamper=False)
    text = "\n".join(p.read_text("utf-8") for p in out.iterdir())
    secrets = [PASSWORD, *world.ctx.secrets.webhook_secrets("prov_b")]
    secrets.append(world.ctx.secrets.jwt_private_pem())
    for secret in secrets:
        assert secret not in text
    for marker in ("eyJ", "Bearer ", "X-MFA-Proof", "mfa_", "refresh_token", "BEGIN"):
        assert marker not in text, marker
