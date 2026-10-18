"""Demo helper: edit one audit row directly in the database, then restore it.

This simulates an attacker (or careless DBA) with direct database access. The application
role cannot do this because of the append-only triggers; this script drops the UPDATE
trigger, edits the row and puts the trigger back. Verify must then FAIL at that sequence.

    python -m app.scripts.tamper_audit            tamper with a recent event
    python -m app.scripts.tamper_audit --seq 7    tamper with event 7
    python -m app.scripts.tamper_audit --restore  put the original value back
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from pathlib import Path
from typing import Any

from app.core.config import get_settings
from app.core.db import AUDIT_TRIGGERS, Database

_SELECT = "SELECT amount_minor, reason_code FROM audit_events WHERE seq = ?"
_SET_AMOUNT = "UPDATE audit_events SET amount_minor = ? WHERE seq = ?"
_SET_REASON = "UPDATE audit_events SET reason_code = ? WHERE seq = ?"


def _backup_path(db_path: Path) -> Path:
    return db_path.with_name("tamper_backup.json")


def tamper_row(db_path: Path | str, seq: int) -> dict[str, Any]:
    """Edit event `seq` behind the application's back. Returns what was changed."""
    path = Path(db_path)
    con = sqlite3.connect(path)
    try:
        row = con.execute(_SELECT, (seq,)).fetchone()
        if row is None:
            raise LookupError(f"No audit event with seq {seq}")
        if row[0] is not None:
            change = {"seq": seq, "column": "amount_minor", "original": row[0], "new": row[0] + 100}
            statement = _SET_AMOUNT
        else:
            change = {"seq": seq, "column": "reason_code", "original": row[1], "new": "TAMPERED"}
            statement = _SET_REASON
        con.execute("DROP TRIGGER IF EXISTS audit_events_no_update")
        con.execute(statement, (change["new"], seq))
        con.execute(AUDIT_TRIGGERS[0])
        con.commit()
    finally:
        con.close()
    _backup_path(path).write_text(json.dumps(change), encoding="utf-8")
    return change


def restore_row(db_path: Path | str) -> dict[str, Any]:
    """Undo the last tamper_row() so the chain verifies again."""
    path = Path(db_path)
    change = json.loads(_backup_path(path).read_text(encoding="utf-8"))
    statement = _SET_AMOUNT if change["column"] == "amount_minor" else _SET_REASON
    con = sqlite3.connect(path)
    try:
        con.execute("DROP TRIGGER IF EXISTS audit_events_no_update")
        con.execute(statement, (change["original"], change["seq"]))
        con.execute(AUDIT_TRIGGERS[0])
        con.commit()
    finally:
        con.close()
    _backup_path(path).unlink(missing_ok=True)
    return change


def _latest_seq(db_path: Path) -> int:
    con = sqlite3.connect(db_path)
    try:
        row = con.execute("SELECT MAX(seq) FROM audit_events").fetchone()
    finally:
        con.close()
    return int(row[0] or 0)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawTextHelpFormatter
    )
    parser.add_argument("--seq", type=int, help="sequence number to edit (default: second newest)")
    parser.add_argument("--restore", action="store_true", help="undo the previous tamper")
    parser.add_argument("--db", help="path to the SQLite file (default: from DATABASE_URL)")
    args = parser.parse_args(argv)

    db_path = (
        Path(args.db) if args.db else Path(Database(get_settings().database_url).sqlite_path())
    )
    if args.restore:
        change = restore_row(db_path)
        print(f"Restored event {change['seq']}: {change['column']} back to {change['original']!r}.")
        return 0
    seq = args.seq or max(1, _latest_seq(db_path) - 1)
    change = tamper_row(db_path, seq)
    print(
        f"Edited audit event {seq}: {change['column']} "
        f"{change['original']!r} -> {change['new']!r}.\n"
        "Now press Verify in the Audit screen (or GET /api/v1/audit/verify): it must FAIL at "
        f"sequence {seq}.\nUndo with: python -m app.scripts.tamper_audit --restore"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
