"""Regressions for the independently reviewed release; all credentials below are synthetic."""

from __future__ import annotations

import importlib.util
import json
import sqlite3
from dataclasses import replace
from pathlib import Path

import pytest

from app.ai.dialogue.policy import reviewed_action
from app.ai.dialogue.state import Action, DialogueState, SlotState
from app.audit.chain import GENESIS
from app.domain.chain_service import ChainService, _tx_hash
from tests.helpers import World, rewrite_audit_consistently

ROOT = Path(__file__).resolve().parents[2]


def script(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_json_credentials_are_scanned(tmp_path, monkeypatch):
    scanner = script("scan_repo")
    monkeypatch.setattr(scanner, "ROOT", tmp_path)
    path = tmp_path / "settings.json"
    path.write_text(json.dumps({"credential": "hf_" + "A" * 30}))
    assert any("Hugging Face" in h for h in scanner.scan_file(path))
    path.write_text(json.dumps({"jwt_signing_key": "A" * 32}))
    assert any("secret assigned" in h for h in scanner.scan_file(path))
    path.write_text(json.dumps({"private": "-----BEGIN " + "PRIVATE KEY-----"}))
    assert any("private key" in h for h in scanner.scan_file(path))


def test_fallback_prunes_builds_but_keeps_benchmark_data(tmp_path, monkeypatch):
    scanner = script("scan_repo")
    monkeypatch.setattr(scanner, "ROOT", tmp_path)
    for name in (
        "web/.next/a.json",
        "web/out/index.html",
        "web/node_modules/x.js",
        "ml/data/a.txt",
        "app.py",
        ".env",
    ):
        path = tmp_path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("synthetic")
    found = {p.relative_to(tmp_path).as_posix() for p in scanner._walk()}
    assert found == {"ml/data/a.txt", "app.py", ".env"}
    assert scanner.scan_file(tmp_path / ".env")


def test_symlinks_never_enter_source_walk(tmp_path, monkeypatch):
    scanner = script("scan_repo")
    monkeypatch.setattr(scanner, "ROOT", tmp_path)
    (tmp_path / "outside-link").symlink_to(ROOT / "README.md")
    assert scanner._walk() == []


@pytest.mark.parametrize("turns", [0, 5, 99])
def test_review_cannot_be_skipped_by_a_turn_budget(turns):
    amount = SlotState(True, False, "both", 0.99)
    state = DialogueState("PLAN", amount=amount, turns=turns)
    assert reviewed_action(state, Action.RUN) == Action.ASK_DATE
    state = replace(state, date_skipped=True)
    assert reviewed_action(state, Action.RUN) == Action.CONFIRM
    assert reviewed_action(replace(state, confirmed=True), Action.RUN) == Action.RUN


def test_conflicted_slots_are_clarified_even_with_forged_confirmation():
    amount = SlotState(True, False, "both", 0.99)
    conflict = SlotState(True, True, "model", 0.9)
    state = DialogueState("CADENCE", amount=amount, months=conflict, confirmed=True)
    assert reviewed_action(state, Action.RUN) == Action.ASK_MONTHS
    state = replace(state, task="PLAN", date=conflict)
    assert reviewed_action(state, Action.RUN) == Action.ASK_DATE
    state = replace(state, amount=conflict)
    assert reviewed_action(state, Action.RUN) == Action.ASK_AMOUNT


def test_independent_checkpoint_detects_coordinated_database_rewrite(tmp_path):
    checkpoint = script("audit_checkpoint")
    data = tmp_path / "database"
    data.mkdir()
    world = World(data)
    try:
        db = world.ctx.db
        with db.write() as session:
            world.ctx.chain.anchor_audit(session, world.ids["admin"])
        dbpath = data / "test.db"
        trusted = tmp_path / "trusted.json"
        checkpoint.create(dbpath, trusted)
        assert checkpoint.verify(dbpath, trusted)["status"] == "PASS"
        with pytest.raises(FileExistsError):
            checkpoint.create(dbpath, trusted)
        with pytest.raises(ValueError):
            checkpoint.create(dbpath, data / "unsafe.json")
        rewrite_audit_consistently(dbpath, 1, "SYNTHETIC: altered by database owner")
        with db.read() as session:
            assert world.ctx.chain.verify_anchors(session)["status"] == "FAIL"
        with sqlite3.connect(dbpath) as con:
            con.row_factory = sqlite3.Row
            hashes = dict(con.execute("SELECT seq, this_event_hash FROM audit_events"))
            con.execute("DROP TRIGGER IF EXISTS chain_log_no_update")
            previous = GENESIS
            for row in con.execute("SELECT * FROM chain_log ORDER BY seq").fetchall():
                args = json.loads(row["args_json"])
                if row["contract"] == "anchor" and row["function"] == "anchor":
                    args[1] = "0x" + hashes[int(args[0])]
                entry = {
                    k: row[k]
                    for k in (
                        "seq",
                        "kind",
                        "contract",
                        "function",
                        "caller",
                        "at",
                        "ref",
                        "actor_id",
                    )
                }
                entry["args"] = args
                digest = _tx_hash(previous, entry)
                con.execute(
                    "UPDATE chain_log SET args_json=?,prev_hash=?,tx_hash=? WHERE seq=?",
                    (json.dumps(args), previous, digest, row["seq"]),
                )
                previous = digest
        fresh = ChainService(world.clock, world.ctx.audit)
        with db.read() as session:
            # This is a LIMITATION regression: the local anchor is not an external trust root.
            assert fresh.verify_anchors(session)["status"] == "PASS"
        assert checkpoint.verify(dbpath, trusted)["status"] == "FAIL"
    finally:
        world.close()
