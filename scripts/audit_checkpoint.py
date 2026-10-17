"""Create/verify a minimal audit checkpoint held OUTSIDE the database directory.

Not a signing service: integrity depends on independently protecting the checkpoint file.
The SQLite connection is read-only; no application secrets or personal fields are exported.

python scripts/audit_checkpoint.py create --db /srv/data/studyroute.db --checkpoint /safe/head.json
python scripts/audit_checkpoint.py verify --db /srv/data/studyroute.db --checkpoint /safe/head.json
"""
from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from datetime import UTC, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
from app.audit.chain import HASHED_FIELDS, verify_events  # noqa: E402


def read_chain(db: Path) -> list[dict]:
    with sqlite3.connect(db.resolve().as_uri() + "?mode=ro", uri=True) as con:
        con.row_factory = sqlite3.Row
        fields = (*HASHED_FIELDS, "this_event_hash")
        columns = ", ".join('"' + name + '"' for name in fields)
        return [dict(row) for row in con.execute(f"SELECT {columns} FROM audit_events ORDER BY seq")]


def create(db: Path, checkpoint: Path) -> dict:
    if checkpoint.resolve().is_relative_to(db.resolve().parent):
        raise ValueError("Checkpoint must be outside the database directory; protect it separately.")
    rows = read_chain(db)
    verdict = verify_events(rows)
    if not verdict.ok or not rows:
        raise ValueError("Refusing to checkpoint an empty or invalid audit chain.")
    result = {"format": "studyroute-checkpoint-v1", "seq": verdict.last_seq,
              "hash": verdict.last_hash, "created_utc": datetime.now(UTC).isoformat()}
    # Exclusive create: never silently replace a previously trusted checkpoint.
    with checkpoint.open("x", encoding="utf-8") as handle:
        json.dump(result, handle, indent=2)
        handle.write("\n")
    checkpoint.chmod(0o400)
    return result


def verify(db: Path, checkpoint: Path) -> dict:
    trusted = json.loads(checkpoint.read_text(encoding="utf-8"))
    if trusted.get("format") != "studyroute-checkpoint-v1":
        raise ValueError("Unsupported checkpoint format.")
    seq = trusted["seq"]
    if not isinstance(seq, int) or seq < 1:
        raise ValueError("Invalid checkpoint sequence.")
    rows = read_chain(db)
    verdict = verify_events(rows)
    row = next((r for r in rows if r["seq"] == seq), None)
    matches = row is not None and row["this_event_hash"] == trusted["hash"]
    return {"status": "PASS" if verdict.ok and matches else "FAIL",
            "chain_valid": verdict.ok, "checkpoint_matches": matches,
            "checkpoint_seq": seq, "events_checked": verdict.events_checked,
            "trust_requirement": "Checkpoint must be independently protected from the DB owner."}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("create", "verify"))
    parser.add_argument("--db", type=Path, required=True)
    parser.add_argument("--checkpoint", type=Path, required=True)
    args = parser.parse_args()
    try:
        result = create(args.db, args.checkpoint) if args.action == "create" else verify(args.db, args.checkpoint)
    except (ValueError, OSError, sqlite3.Error, KeyError) as exc:
        print(f"Checkpoint error: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(result, indent=2))
    return 1 if result.get("status") == "FAIL" else 0


if __name__ == "__main__":
    raise SystemExit(main())
