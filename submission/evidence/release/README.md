# Current repair-release evidence

Read `VERIFICATION.md` for final counts and scope. New files here are generated or recorded during
this repair, not borrowed performance claims. The application runs entirely on synthetic data.

- `nlu-reproduction.log` and `../ai_evaluation.json`: all six NLU splits rerun, with model/source/data
  hashes and runtime provenance. Frozen blind data is reused; not a new independent study.
- `rl-reproduction.log` and `../ai_rl_evaluation.json`: raw learned policy and all runnable baselines
  on the same 6,000 synthetic test conversations. Runtime mandatory review is NOT included.
- `corridor_sources.json`: primary-source facts and explicit missing live validation.
- Backend JUnit/log, web logs, ruff and build logs: exact local verification results.
- `demo-recording.json` and MP4: actual local browser interaction with the repaired UI and real
  local backend; synthetic credentials, no real money, no fabricated panels or overlay claims.

Parent-directory operation/tamper evidence is refreshed with `app.scripts.export_evidence --tamper`.
`docker_run.txt`, `docker_telemetry_capture.txt`, backbone training ablations and old screenshots are
**inherited historical material**, not fresh verification of this repair. Docker is unavailable here;
cloud provider calls, deployed HTTPS, external immutable anchoring and real bank quotes are untested.
Model training was not rerun. Do not cite old test counts or latency as newly verified.

Checkpoint regression: normal PASS → audit-only rewrite FAIL → coordinated audit+chain rewrite PASS
(local limitation) → independently retained checkpoint FAIL. The checkpoint is useful only when
protected from the database owner. This regression is in `test_release_hardening.py`, not a claim
that a public or consortium blockchain was deployed.
