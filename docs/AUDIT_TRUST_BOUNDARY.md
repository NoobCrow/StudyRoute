# Audit trust boundary and external checkpoints

## What is and is not protected
- SHA-256 chaining plus append-only triggers detects accidental edits, incomplete edits and
  ordinary application-level update attempts. A privileged SQLite file owner can drop triggers.
- The in-memory EVM persists by replaying `chain_log` from the SAME SQLite database as `audit_events`.
  It survives restart, but is not an independent external anchor.
- An audit-only rewrite and rehash produces a local anchor mismatch. A coordinated rewrite and
  rehash of **both** logs can pass after restart. This is a database-owner threat, not evidence of
  a remote unauthenticated exploit.
- `backend/tests/test_release_hardening.py` reproduces both cases. We keep the passing coordinated
  rewrite as a **limitation regression**, rather than hiding it with a misleading security claim.

## Minimal independently protected checkpoint
Run from the project root using the backend environment:

```bash
python scripts/audit_checkpoint.py create --db /srv/studyroute/data/studyroute.db --checkpoint /safe-reviewer/head-001.json
python scripts/audit_checkpoint.py verify --db /srv/studyroute/data/studyroute.db --checkpoint /safe-reviewer/head-001.json
```

The tool opens SQLite read-only, verifies the complete hash chain before creating a checkpoint,
exports only sequence/hash/time, refuses overwrite and refuses a checkpoint in the database directory.
Verification allows new appended events but rejects deletion or rewriting of the trusted prefix.
Exit codes: 0 success, 1 failed verification, 2 invalid input or operational error.

**A different directory alone does not establish independence.** Transfer the checkpoint to a
reviewer's separately administered read-only storage, signed timestamp service or object-lock bucket.
Permissions `0400` are defence in depth, not protection from the same OS administrator. If the attacker
can replace both the database and checkpoint, this scheme provides no integrity guarantee. No automatic
external service or immutable/public-chain anchoring is deployed in this release.

A checkpoint protects only the previously recorded prefix. An operator must set checkpoint frequency,
review missing intervals and protect the database identity out of band; sequence/hash does not prove
that an uncheckpointed tail is complete or that economic events are truthful.
