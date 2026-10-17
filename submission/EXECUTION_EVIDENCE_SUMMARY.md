# StudyRoute: execution evidence (summary)

International Track deliverable 06. StudyRoute is a **sandbox**: every account, provider, FX rate, KYC
result, bank message and settlement below is simulated and every record is synthetic. No real money
moved and no real bank, FX feed or identity service was contacted. The raw files are in
`submission/evidence/` (in the repository and in the archive); this page says what each one shows.

## What the logs show

| Evidence | File | What it shows |
|----------|------|---------------|
| Sandbox operation log | `sandbox_operation_log.txt` | The 14-step demo run against the API: deadline planner, three providers ranked by true total cost, the assistant and agent tasks, a draft made safe to retry (Idempotency-Key), the KYC gate, approval by a human parent with a fresh MFA proof, a forged webhook and a prompt injection refused, simulated settlement and tracker, a sealed compliance report, the bank network, smart escrow and the audit-chain check. **66 checks OK, 0 failed.** |
| Audit log | `audit_log.json` | All **75** audit events of that run in order, each with `prev_event_hash` and `this_event_hash` (SHA-256 chain). |
| Audit verification | `audit_verify.json` | The chain verified: **PASS**, 75 events checked, head hash `0e76a9fc...ae33a`. |
| Tamper demonstration | `tamper_demo.json` | One amount was edited behind the application's back (event 74): verification answered **FAIL** (hash mismatch at 74). After the edit was undone it answered **PASS** (75 events). |
| Payments | `payments.json` | The payment with its state timeline (DRAFT, QUOTED, PENDING_APPROVAL, APPROVED, SUBMITTED, SETTLED) and its UETR. |
| Bank network | `bank_network.json` | Simulated national and international transfers with every hop, the simulated messages and double-entry journals, and the trial balance. |
| Smart escrow | `smart_escrow.json` | The escrow schedule, the contract call log with hashes, the simulated chain's status and the audit anchors. |
| AI risk score and bank review desk | `review_demo_run.txt` | Six payments scored by the trained model; one warned and waited for the bank's reviewer, who asked a question, got an answer and said yes with a fresh MFA proof; the parent then authorised it with MFA. The parent could not approve while the review was open. |

## Security tests (18 October 2026, throwaway lab databases)

Raw output in `security_2026-10-18/`. A result of PASS means the attack was **defended**.

| Tool | Result |
|------|--------|
| Attack probe (anonymous access to every route, forged tokens, cross-household access, injection, hostile input, CORS, webhooks, the bank review desk) | 146 of 146 defended |
| Brute force and lockout, rate limits, user enumeration | 8 of 8 |
| Data-leak scan (canary secrets in the database, logs and responses) | all clear, 50 checks |
| Man in the middle (changed approval, stripped or swapped MFA proof, replays, forged webhooks) | 14 defended, 0 failed |
| Assistant as an attack target (hostile prompts as parent and student) | 42 of 42 |
| Real Chrome through every screen under the production CSP, including the Bank review screen | 48 of 48 |

These probes were written by the team that wrote the app. **No independent penetration test has been done.**

## Running it in Docker (18 October 2026)

Raw output in `docker_2026-10-18/`, the full record in `docker_run.txt`. In a Linux VM (Ubuntu 24.04,
Docker 29.1.3) from the unzipped submission archive: `docker compose up --build` made both containers healthy;
the smoke script passed; the 14-step demo passed (66 OK lines); the AI risk and bank review demo passed; the
real-Chrome audit passed 48 of 48; the audit chain verified across a restart with the data kept; and the hardened
overlay (read-only filesystem, all capabilities dropped) passed smoke and the demo. The first demo run found a real
problem (the trained explainer reworded the assistant's questions, and the demo's checks were too strict about it);
the failing run is kept as `demo_flow_before_fix_3_failures.txt` beside the run after the fix.

## Tests

1,678 backend tests (1,677 passed, 1 skipped on Windows), 463 web tests and 24 browser tests in the last full
runs; one test or more per blueprint scenario T01 to T24. See `docs/TEST_CASES.md` and
`submission/evidence/release/VERIFICATION.md`.

## AI evaluations

`ai_evaluation.json` (trained reader against rules), `ai_rl_evaluation.json` (dialogue policy),
`ai_explainer_evaluation.json` (explainer), `ai_risk_training.json`, `ai_risk_ablation.json`,
`ai_risk_operating_points.json` and `ai_risk_model_comparison.json` (risk model, all models compared). Each states
its own limits: the risk model was trained on public synthetic transaction data, so its precision and recall
(about 29% and 56% at the bank desk's setting) are for a router that decides who a person looks at, not for
real fraud detection.

## Demo video

`submission/StudyRoute_Demo.mp4` is a short recording of the actual local UI and API with English subtitles and no
voice-over. The team's voiced pitch video is delivered separately.

## What this evidence does not show

- Anything with a real bank, a real FX feed or real people: the sandbox does not have them.
- An outside review of the code or the security tests.
- Real-world calibration: provider fees, spreads and city costs are invented.
- The packet capture, the screen tours and the in-container test suites were not repeated in the Docker run of
  18 October (earlier runs are recorded in `docker_run.txt`).
