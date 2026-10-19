# StudyRoute — Execution Evidence Report

What we ran, what happened, and where the raw files are

SR-EVD-2026-01 | Run on 18 October 2026, updated 20 October 2026

## Summary

This report shows what happened when we ran StudyRoute on a clean machine and drove it end to end. Everything is synthetic: the providers, the KYC results, the rails and the settlements are all simulated, no real money moved and no live bank was contacted.

We ran the full backend test suite, played the whole 14-step payment demonstration against a real local API, edited an audit record on purpose to see the chain break, and checked the bank ledger and the AI components. The table below is the short version. Each row names the evidence file behind it (E01 to E07, listed under Repeating it yourself).

| What we checked | Result | Evidence |
| --- | --- | --- |
| Full backend regression | 1,672 passed, 0 failed, 1 skipped (1,673 collected) | E01 |
| Local API demonstration | 14 steps, 66 checks OK, 0 failed | E02 |
| Audit chain, untouched | PASS, 76 events | E03 |
| Audit chain after we edited event 75 | FAIL at event 75; PASS again after restoring it | E03 |
| Chain recomputed offline, outside the app | Valid; the altered copy is rejected | E05 |
| Bank ledger | Balanced in all 7 currencies | E04 |
| AI components | Reader, dialogue policy, risk model and local explainer all load | E06 |
| Repository scan for secrets and TODOs | Clean | E06 |

## What we ran it on

We took the source archive of commit bcce930 of NoobCrow/StudyRoute (834 files, SHA-256 4e6ce74c…74134a) and ran it on 18 October 2026 between 10:07 and 10:08 UTC.

| Item | Setting |
| --- | --- |
| System | Linux, Python 3.13.14, pytest 9.1.1 |
| App | FastAPI 0.143.0, SQLAlchemy 2.1.4, a throwaway SQLite database |
| Local AI | ONNX Runtime 1.31.0, sentencepiece 0.2.2 |
| Network | API bound to 127.0.0.1:18763 only |
| Settings | sandbox mode, all four model modes on auto, cloud assistant off |

The demonstration used the real application, worker, database and local models. Simulated providers sent signed callbacks into the local API. The backend tests use in-process clients and fake clocks, and many of them turn the models off so they can check the deterministic rules on their own.

We did not do a clean dependency install, a frontend build, a browser run, a Docker run or any model training for this report. The health field `ai_mode=llm` means the local trained explainer is in use, not a remote model call; we confirmed that with a separate load check.

## Backend tests

We ran the complete backend suite without changing any application code: **1,672 passed, 0 failed, 0 errors, 1 skipped**, out of 1,673 collected, in 375.54 seconds. The per-test results are in the JUnit file (E01).

```text
cd StudyRoute-main/backend
python -m pytest -o addopts='' -q --junitxml=../../validation/backend-current.xml
```

The skipped item was a whole module, `test_explainer_model.py`. Its data file, `backend/tests/data/explainer_cases.json`, was missing from the archive because the repository's `.gitignore` rule for `data/` had excluded it. So its quality-floor tests did not run that day. We fixed this on 19 October by committing the file, and a full run on our Windows machine now collects 1,705 tests, 1,704 passing and 1 skipped (a symlink test), including a new 25-prompt assistant suite. That later run is not part of the 18 October execution and its output is not in the evidence bundle. The 1,705 figure is the one used in the technical documentation, the deck and the README.

The suite covers sign-in and sessions, roles and household isolation, payment guards and idempotency, signed provider webhooks, the audit chain, document encryption at rest, the bank ledger and review desk, escrow, and the AI number guard and red-team checks. It shows that these assertions hold; it is not a claim of complete coverage.

## The 14-step demonstration

The `export_evidence` runner drives the real local API and prints one OK or FAIL line per assertion. The whole flow gave 66 OK and no failures (E02). The table is an index to that transcript.

| Step | What happens | What we saw |
| --- | --- | --- |
| 1 | Dashboard and deadline | A synthetic tuition goal and deadline are there |
| 2 | Compare providers | Three synthetic providers ranked by total cost, not a live quote |
| 3 | Explain the comparison | The assistant answers from the engine's facts |
| 4 | Sentence to plan | Planning stays separate from sending; a human decision is still needed |
| 5 | Draft and safe retry | The same idempotency key returns the same payment, not a second one |
| 6 | KYC gate | The request is blocked until the mock identity check is done |
| 7 | Prepare to authorise | Mock KYC reviewed; recipient allowlisted with the step-up code |
| 8 | Approve | Student and wrong-code attempts refused; parent with a valid code accepted; replay is harmless |
| 9 | Hostile inputs | A forged webhook is rejected; a prompt-injection instruction is refused |
| 10 | Tracker | The payment moves through submission to simulated settlement |
| 11 | Compliance report | A report with an integrity hash is produced (not a legal attestation) |
| 12 | Bank network | Synthetic national and international transfers, a return, and balancing entries |
| 13 | Smart escrow | Tranche and freeze behaviour on a local simulated EVM, no real tokens |
| 14 | Audit chain | Verification passes; the tamper experiment is exported separately |

The exported payment is a synthetic GBP 10,000.00 tuition payment through Provider B, ending in SETTLED with a UETR-style tracking id. Ids and timestamps change on every run, so the raw JSON is the authority (E04).

Two things to keep in mind. SETTLED here means a simulated provider's callback moved our own state machine; it says nothing about a bank transfer or SWIFT delivery. And the sandbox MFA code and mock KYC are not meant for real identity checks.

## Audit tamper experiment

Every event in the audit log stores the hash of the one before it. To see that this really works, we changed one stored amount on a throwaway database and asked the app to verify the chain.

| Stage | Result | File |
| --- | --- | --- |
| Before the edit | PASS, 76 events | audit_verify.json |
| Edit amount_minor of event 75 | FAIL, HASH_MISMATCH at event 75 | tamper_demo.json |
| Restore the original row | PASS, 76 events | tamper_demo.json |
| Offline recomputation of the fresh chain | Valid; altered copy rejected at 75 | evidence-integrity-check.json |
| Offline recomputation of the chain that came with the archive | 75 events valid; altered copy rejected at 74 | evidence-integrity-check.json |

The audit head after the run was `0e0ff18d559f93c6003fefe7cbb389e5037d93a06540687f372754461137678c`.

One detail cost us time: the API export adds a display field, `amount_display`, that is not stored and is not hashed. The hash covers only the stored fields in `HASHED_FIELDS`, so the offline check has to leave out `amount_display` and `this_event_hash`. If you include them you get a false mismatch.

There is also a limit we want to state plainly. Someone who owns the database and rewrites both the audit log and the simulated chain can still pass the local checks. A checkpoint kept somewhere separate will expose a changed prefix, and the test suite has a test for exactly this, but it is not the same as external immutability. Only run the tamper script on disposable data.

## Ledger and escrow

The bank network snapshot reports `all_ok=true`. Debits equal credits in all seven currencies, the mirror accounts are reconciled and the mismatch list is empty (E04). These are consistency checks on invented accounts.

| Currency | Debits (minor units) | Credits (minor units) |
| --- | --- | --- |
| AUD | 8,050,000,000 | 8,050,000,000 |
| BDT | 61,604,821,000 | 61,604,821,000 |
| CAD | 8,050,000,000 | 8,050,000,000 |
| EUR | 8,050,000,000 | 8,050,000,000 |
| GBP | 50,120,980,000 | 50,120,980,000 |
| MYR | 8,050,000,000 | 8,050,000,000 |
| USD | 8,050,000,000 | 8,050,000,000 |

| Transfer | Final state | Journal records |
| --- | --- | --- |
| National | SETTLED | 4 |
| International | SETTLED | 4 |
| International | RETURNED | 6 |

The export has one escrow with its contract-call records and one audit anchor. The simulated chain reports ready and the anchor comparison passes. It runs on py-evm, an in-memory EVM with no peers and no real tokens. Balanced books do not prove the transactions are realistic, and none of this validates real rail limits, fees or a production contract.

## The AI components

On this run we confirmed that the Reader, DialoguePolicy, RiskScorer and the local explainer load and take part in the live demonstration with the cloud path off (E06). We did not retrain anything or run a new accuracy study. The figures below come from our own evaluation files and were not re-run for this report.

| Measure | Value | How to read it |
| --- | --- | --- |
| Reader, blind routing | 100 of 113 (88.50%) | A frozen holdout we measured earlier |
| Reader, attack blocking | 13 of 14 blind, 18 of 20 hard | Small sets, and some attacks get through, so authorisation never depends on the filter |
| Dialogue policy, wrong plans | 50 in 6,000 | Before runtime review |
| Ask-everything-and-confirm baseline | 1 in 6,000 | The learned policy is not safer than this baseline in our simulator |
| Risk desk, medium and high | Precision 29.22%, recall 56.48% | Synthetic data; it routes payments to a person, it is not a fraud detector |
| Explainer, output accepted | 80.86% of 700 pairs | Rewrites that fail the checks fall back to the engine's text |

None of these numbers give the AI any power to approve; approval stays with the deterministic rules and a human with a fresh MFA code.

## Earlier results and checks made later

These records came with the source and we did not re-run them.

| Record | Result | Note |
| --- | --- | --- |
| release/backend.xml | 1,542 cases, no failures | An earlier full run; overlaps with the current one |
| release/backend-final-regression.xml | 42 cases, no failures | Focused wording and review checks |
| release/packaging-recheck.xml | 53 cases, no failures | Packaging and preflight |
| release/web-tests.log | 439 web unit and component cases | Taken before the bank-review screens' tests were merged; the merged tree has 463 (docs/TEST_CASES.md) |
| release/browser-tests.log | 24 browser smoke tests | Static UI with a mocked API |
| security_2026-10-18/ | 146/146 attacks, 8/8 abuse, 42/42 assistant, 14 MITM defended, 48/48 browser | Our own probes, not an independent pentest |
| release/demo-recording.json | 5 scenes, 95-second recording of the real local UI and API | Not the full MFA-to-settlement path |

We do not add these counts together; the 18 October JUnit file (E01) is the current backend result.

After the run we also checked the repository itself (E07). The remote main branch is commit bcce930, the one this report covers. The repository is public and its README, technical documentation PDF and deck load without signing in. GitHub shows the "ci" workflow on that commit as successful (run 39081290614): docker, contracts, web, secret scan, backend and dependency audit. We did not read the job logs again.

Separately, in an Ubuntu 24.04 VM with Docker 29.1.3 we ran the smoke checks, the 14-step demo (66 checks OK), the bank-review demo, a real-Chrome audit (48 of 48) and the hardened overlay with a read-only filesystem and all capabilities dropped. They passed. That run used the archive of commit 8d91cc8 with the files of fix c9d044b copied in, so it was not a fresh archive of bcce930, and we did not repeat it for this report. It first showed that the trained explainer was rewording the assistant's questions, which made three demo checks fail; the fix is in bcce930. The raw output is in inherited/submission/evidence/docker_2026-10-18/.

## Repeating it yourself

Use a separate workspace and synthetic data only.

```text
cd StudyRoute-main/backend
python -m venv .venv
python -m pip install -r requirements-dev.txt
python -m pytest -o addopts='' -q --junitxml=backend-current.xml
```

For the live demonstration, set a new `DATA_DIR` and `DATABASE_URL` outside the source tree, with `APP_ENV=sandbox`, `WEBHOOK_BASE_URL=http://127.0.0.1:18763`, all four model modes on auto and no cloud keys. Then:

```text
python -m app.scripts.seed --if-empty
python -m uvicorn app.main:create_app --factory --host 127.0.0.1 --port 18763 --no-access-log

# in a second terminal, same environment
python -m app.scripts.export_evidence --base-url http://127.0.0.1:18763 --out /path/to/new-evidence --tamper
python scripts/scan_repo.py
```

The `--tamper` option edits an audit row and restores it, so it belongs on disposable data only. Never use it, or `--reset`, on a deployment. The helper scripts we used (`tools/run_live.py`, `tools/inspect_evidence.py`) have the paths of our workspace in them; change those before reusing them.

### Where the files are

| ID | What it is | Files |
| --- | --- | --- |
| E01 | Full backend regression | validation/backend-current.log, .xml, .exit |
| E02 | Live API demonstration | validation/live-run.json, live-export.log, live-evidence/sandbox_operation_log.txt |
| E03 | Audit and tamper evidence | live-evidence/audit_log.json, audit_verify.json, tamper_demo.json |
| E04 | Payments, ledger and escrow | live-evidence/payments.json, bank_network.json, smart_escrow.json |
| E05 | Source identity and offline chain check | validation/source-identity.json, source-file-inventory.json, evidence-integrity-check.json |
| E06 | Source scan and model loading | validation/source-scan.log, environment-models.json, rbac-matrix.json |
| E07 | Remote repository and CI check | validation/final-verification.json |

`SHA256SUMS.txt` in the evidence pack lets you check the files are unchanged. That only shows they match the list; it is not a signature. The database, generated keys and `dev_secrets.json` are deliberately left out.

## What this does and does not show

It shows that the source we submitted runs, passes its own tests, and behaves as described in a synthetic local demonstration, including the approval rules and the tamper-evident audit log. It does not show a public deployment, an independent security review, real-world model accuracy, regulatory approval or a live bank, FX or KYC connection. For the open risks, read the Security Self-Assessment. We have not sent the submission e-mail or given anyone access to the repository as part of this report.
