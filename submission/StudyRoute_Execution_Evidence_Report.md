# StudyRoute — Execution Evidence Report
Reproducible local execution with traceable raw evidence

SR-EVD-2026-01 | 18 October 2026

> Synthetic-data demonstrator. Self-assessment, not production certification.

## Final-submission update
*00 / VERIFIED AFTER THE ORIGINAL ASSESSMENT*

The original execution evidence in this document (18 October 2026) is unchanged: every result and count below stands as written. This page adds read-only checks made later the same day, recorded in validation/final-verification.json (E07, produced by tools/final_verification.py), and supersedes the original statement that the remote repository was not checked. This page is the final-submission update; its skipped-test-module row and the canonical counts were revised on 19 October 2026.

| Item | Result |
| --- | --- |
| Source identity | The remote main branch of NoobCrow/StudyRoute is commit bcce930ae0974712e922245878fd976b03a8938a, the commit this document covers. The original assessment could not check the remote; this supersedes its statements that the remote HEAD was not checked. [E07] |
| Repository access | Public; default branch main. The README, the technical-documentation PDF and the deck load anonymously (HTTP 200). [E07] |
| Continuous integration | GitHub reports the workflow "ci" on that commit as success: docker, contracts, web, secret-scan, backend and dependency-audit all succeeded (run 39081290614). The job logs were not re-reviewed here. [E07] |
| Other branches | A branch named botkeep (3 commits, head e2c28a0c74b6) is on the remote and is not part of main. It was not assessed; this document still covers main only. [E07] |
| The skipped test module (closed) | In the 18 October run backend/tests/test_explainer_model.py was skipped because its fixture, backend/tests/data/explainer_cases.json, was excluded by the repository's .gitignore rule data/ and so was absent from the public repository and from the archive; a fresh clone collected 1,673 tests, ran 1,672 and skipped the explainer quality-floor tests, which is exactly the result recorded in this report. Closed on 19 October 2026: the fixture is now committed (a narrow .gitignore exception) and included in the offline source archive, and a full backend run on the team's Windows machine collects 1,705 backend tests (1,704 pass, 1 skipped on Windows, a symlink test), including a new 25-prompt assistant suite. That 19 October run is not part of the execution recorded here and its output is not in the evidence bundle. |
| The team's Docker run (inherited, not re-run here) | Same day, in an Ubuntu 24.04 VM with Docker 29.1.3: the smoke checks, the 14-step demo (66 checks OK), the bank-review demo, a real-Chrome audit (48 of 48) and the hardened overlay (read-only filesystem, all capabilities dropped) passed. The run used the archive of commit 8d91cc8 with the two files of the later fix c9d044b copied in; it was not a fresh archive of bcce930. It first found that the trained explainer reworded the assistant's questions (3 demo checks failed; the CI docker job had failed 4); the fix is part of bcce930. Raw output: inherited/submission/evidence/docker_2026-10-18/ and docker_run.txt (H04). |
| Corrections to the original assessment | Section 10 says the supplied web log's 439 cases are real and that an older summary says 463. The order is the reverse: 439 comes from the teammate's release log, taken before the merge that added the bank-review screens' tests, and 463 is the count on the merged tree (docs/TEST_CASES.md; the team's own run, not re-run here). [E07] |

**Canonical counts.** The execution recorded in this report is the 18 October run: 1,672 passed / 1 skipped, with 1,673 collected, on the archive before the explainer fixture was added. The current backend count, quoted by the technical documentation, the deck and the README, is 1,705 (1,704 pass, 1 skipped on Windows).

> **Not changed by this update** — The 1,672-test regression, the 66-check API demonstration, the audit tamper and restore experiment, the ledger and escrow checks, the reproduction procedure and the acceptance boundary.

## Evidence at a glance
*01 / REVIEWER SUMMARY*

This report documents repeatable local execution of the supplied StudyRoute source and distinguishes it from evidence inherited with that source. Every financial account, provider, KYC result, rail and settlement in the demonstration is synthetic. No real money moved and no live banking service was contacted. [E01–E06]

| Freshly checked | Result | Evidence |
| --- | --- | --- |
| Complete backend regression | 1,672 passed / 0 failed / 0 errors / 1 skipped | E01 |
| Local HTTP API demonstration | 14 steps; 66 OK; 0 FAIL; exit 0 | E02 |
| Audit baseline | PASS; 76 events | E03 |
| Deliberate audit edit / restoration | FAIL at sequence 75 / PASS after restore | E03 |
| Offline chain recomputation | Supplied 75 and fresh 76 events valid | E05 |
| Bank ledger / mirrors | all_ok=true; 7 currencies balanced | E04 |
| Local AI component loading | Reader, policy, risk and local explainer loaded | E06 |
| Repository pattern scanner | Exit 0; no configured-pattern findings | E06 |

### How to read the package

- Read this report for scope, scenario results and interpretation.
- Use EVIDENCE_INDEX.md to locate the raw files behind every claim.
- Use SHA256SUMS.txt to check the delivered artifacts have not changed.
- Read the companion Security Self-Assessment for unresolved production risks.

> **Not a deployment success certificate** — The Botkeep import and its public runtime were not validated here. The fresh evidence is from a local main-source instance, not a live GitHub-connected Botkeep server.

## Provenance & evidence taxonomy
*02 / CHAIN OF CUSTODY*

| Source identity | Value |
| --- | --- |
| Input filename | StudyRoute-main.zip |
| Compressed size | 84,558,543 bytes |
| Archive content | 834 files; 116,683,391 uncompressed bytes |
| Archive-supplied commit | bcce930ae0974712e922245878fd976b03a8938a |
| SHA-256 | 4e6ce74cdafa51e4fa577813444d1f52c7d1d0098a7338b176005b415574134a |
| Repository reference | https://github.com/NoobCrow/StudyRoute |
| Fresh run date | 18 October 2026 (UTC) |

### Three evidence classes

| Class | Meaning | Examples |
| --- | --- | --- |
| FRESH | Executed or recomputed for this report on the extracted supplied source. | Backend JUnit; local API flow; model-load check; source scanner; audit recomputation. |
| SUPPLIED / HISTORICAL | Carried in the archive. Inspected, not rerun unless separately stated. | Web unit tests; browser smoke; Docker logs; AI benchmark JSON. |
| NOT VERIFIED | Outside this review; no supporting execution asserted. | Botkeep deployment; live bank/FX/KYC; independent pentest; external immutable anchor. |

The archive ZIP comment supplies the commit identifier. The final-submission update checked it: the remote main branch is the same commit (E07). source-file-inventory.json records every original archived file’s length and SHA-256 before generated test caches are considered. Raw evidence is copied without rewriting outcomes. [E05]

> **Hash limitation** — A checksum proves consistency with the manifest delivered alongside it; it is not an authenticated digital signature or proof of publisher identity. Keep the delivered digest or package in separately trusted storage.

## Environment & repeatability
*03 / TEST CONDITIONS*

| Component | Observed condition |
| --- | --- |
| Operating environment | Linux-6.18.49-x86_64-with-glibc2.34 |
| Interpreter | Python 3.13.14 |
| Test framework | pytest 9.1.1 |
| API and persistence | FastAPI 0.143.0; SQLAlchemy 2.1.4; disposable SQLite |
| Local inference | ONNX Runtime 1.31.0; sentencepiece 0.2.2 |
| Network boundary | Uvicorn bound to 127.0.0.1:18763; HTTP loopback; no public exposure. |
| Run configuration | APP_ENV=sandbox; all four model modes auto; assistant cloud disabled. |
| Run window | 2026-10-18T10:07:13 to 2026-10-18T10:08:24 UTC |

### Real local integration vs test doubles

The HTTP demonstration starts the real application, worker, SQLite persistence and local model components; simulated providers deliver signed callbacks into the local API. Banking, FX and KYC remain built-in simulations. Backend tests separately use in-process clients, fake clocks and isolated fixtures; many disable models to isolate deterministic behavior. [E01–E02; E06]

### Reproducibility limitations

- Dependencies were reused from the available environment; this is not a clean installation certification.
- No frontend build, desktop/mobile browser suite, Docker run, model training or new benchmark dataset was executed for this report.
- The health field ai_mode=llm identifies a language-model path, not a remote provider call. The independent load check identifies LocalExplainerLLM; operator cloud configuration was disabled.

> **Privacy** — The private local database, generated encryption/signing keys, dev_secrets.json and test caches are intentionally not included in the evidence bundle. Public evidence contains only synthetic scenario data and recorded results.

## Backend regression results
*04 / FRESH — COMPLETE SUPPLIED SUITE*

The complete supplied backend suite was executed without modifying application source. Result: **1,672 passed / 0 failed / 0 errors / 1 skipped**; **1,673 collected cases**, recorded suite duration **375.54 seconds**. Exact test-level outcomes are preserved in JUnit. [E01]

```text
cd StudyRoute-main/backend
python -m pytest -o addopts='' -q \
  --junitxml=../../validation/backend-current.xml
```

> **One module-level skip** — test_explainer_model.py was skipped at collection because backend/tests/data/explainer_cases.json is absent from the supplied archive. The explainer model files are present and a separate fresh load check succeeded. The missing-fixture quality-floor tests were not executed; one skipped JUnit item does not mean only one unexecuted test function.

### Security and financial coverage

| Family | Representative supplied modules |
| --- | --- |
| Identity and sessions | test_api_auth; test_browser_session; test_security_thief |
| Least privilege / tenants | test_rbac; test_api_roles; test_api_ai_rbac; test_security_households |
| Payment guardrails | test_api_payment_guards; test_api_idempotency; test_api_payments |
| Authentic provider events | test_api_webhooks; test_webhook_signing |
| Audit / tamper boundary | test_audit; test_api_audit_config; test_release_hardening |
| Data protection | test_documents_at_rest; test_security_leaks; test_saved_ai_connection |
| Banking / escrow / review | test_ledger; test_api_bank; test_bank_review; escrow and chain modules |
| AI deterministic envelope | test_ai_redteam; test_ai_number_guard; NLU, policy, risk and explainer modules |

> **No double counting** — The supplied 1,542-case suite and focused 42-/53-case logs are inherited runs and overlap. They are not added to this run. Counts in older prose summaries are not used as fresh evidence. Tests demonstrate the supplied assertions, not universal coverage or independent assurance.

## Demonstration: preparation & approval
*05 / FRESH — SCENARIOS 01–08*

The supplied export_evidence runner exercises the real local API and records one OK/FAIL line per assertion. Its complete 14-step flow yielded 66 OK checks and no failed checks. These scenario descriptions are an index to the raw transcript, not reconstructed screenshots. [E02]

| Step | Scenario | Observed behavior |
| --- | --- | --- |
| 01 | Dashboard and deadline | Synthetic tuition goal and deadline are present. |
| 02 | Compare providers | Three synthetic providers ranked by deterministic total cost, not a live quote. |
| 03 | Explain comparison | Assistant answer grounded in available engine facts. |
| 04 | Sentence → plan | Planning remains separate from execution; human decision required. |
| 05 | Draft + safe retry | Same idempotency key returns the same payment rather than duplicating it. |
| 06 | KYC gate | Request blocked while mock KYC requirements are unmet. |
| 07 | Prepare authorization | Mock KYC reviewed; recipient allowlisted using the demo’s step-up path. |
| 08 | Approve safely | Student/insufficient-proof paths refused; parent proof accepted; replay safe. |

### Core invariants

- A conversational suggestion is not authorization to send money.
- The request/approval path re-evaluates its required guards.
- MFA, summary consistency, role and replay constraints are distinct controls.
- All credentials and identities in this run were sandbox fixtures.

> **Demonstration limitation** — The sandbox MFA code and mock KYC are intentionally unsuitable for production identity assurance. “Passed approval” here means the coded synthetic workflow completed, not that a bank or regulator approved a payment.

## Demonstration: settlement & integrity
*06 / FRESH — SCENARIOS 09–14*

| Step | Scenario | Observed behavior |
| --- | --- | --- |
| 09 | Hostile inputs | Forged webhook rejected; tested prompt-injection instruction refused. |
| 10 | Simulated tracker | Payment advances through submission and simulated settlement. |
| 11 | Compliance evidence | Canonical report produced with integrity hash; not a legal compliance attestation. |
| 12 | Bank network | Synthetic national/international transfers, returns and balancing records collected. |
| 13 | Smart escrow | Tranche/freeze-related behavior on local simulated EVM; no network or real tokens. |
| 14 | Audit chain | Verification succeeds; tamper/restore experiment is exported separately. |

![Trust-boundary diagram](assets/payment.png)

### Recorded payment

The exported payment shows a synthetic tuition target of GBP 10,000.00, Provider B (synthetic), final state SETTLED and a UETR-shaped tracking identifier. The recorded debit is an illustrative sandbox amount, not a current market rate or fee commitment. Payment IDs and timestamps are generated per run; the raw JSON is the authority. [E04]

> **What SETTLED means here** — A simulated provider callback advances the local state machine. It is not proof of bank transmission, SWIFT delivery, correspondent credit, reconciliation with a bank statement or irreversible economic finality.

## Audit experiment & independent check
*07 / FRESH — POSITIVE AND NEGATIVE EVIDENCE*

| Stage | Observed result | Artifact |
| --- | --- | --- |
| Baseline | PASS; 76 events checked | live-evidence/audit_verify.json |
| Edit event 75 amount_minor | FAIL; HASH_MISMATCH; failed_seq=75 | live-evidence/tamper_demo.json |
| Restore original row | PASS; 76 events checked | live-evidence/tamper_demo.json |
| Offline recomputation | Fresh 76-event chain valid; altered copy rejected at 75 | evidence-integrity-check.json |
| Supplied chain recomputation | 75-event chain valid; altered copy rejected at 74 | evidence-integrity-check.json |

### Fresh audit head

```text
0e0ff18d559f93c6003fefe7cbb389e5037d93a06540687f372754461137678c
```

### Canonicalization matters

The API export adds amount_display for human readability. The hash covers the stored event fields listed in HASHED_FIELDS, not this derived display field or this_event_hash itself. The offline verifier excludes those two fields, preserves the raw JSON and recomputes SHA-256(previous_hash || canonical_event). Treating amount_display as a stored field would produce a false mismatch. [C06; E05]

### A necessary negative result

The source’s coordinated-rewrite test demonstrates the local trust limit: a database owner who rewrites both audit and simulated-chain logs can pass local checks. A separately protected checkpoint exposes an altered trusted prefix. The fresh complete test suite includes this regression; the report does not relabel that limitation as external immutability. [E01; C06]

> **Safety of reproduction** — The tamper demonstration ran only on the isolated disposable database. Never drop audit triggers, alter records or run tamper scripts on a deployed dataset.

## Ledger & escrow invariants
*08 / FRESH — SYNTHETIC FINANCIAL RECORDS*

The collected bank network snapshot reports all_ok=true. All seven trial-balance currencies have equal debits and credits; mirror accounts report reconciled=true, and the mismatch list is empty. These are internal consistency checks on invented accounts and rails. [E04]

| Currency | Debits — minor units | Credits — minor units | Balanced |
| --- | --- | --- | --- |
| AUD | 8,050,000,000 | 8,050,000,000 | Yes |
| BDT | 61,604,821,000 | 61,604,821,000 | Yes |
| CAD | 8,050,000,000 | 8,050,000,000 | Yes |
| EUR | 8,050,000,000 | 8,050,000,000 | Yes |
| GBP | 50,120,980,000 | 50,120,980,000 | Yes |
| MYR | 8,050,000,000 | 8,050,000,000 | Yes |
| USD | 8,050,000,000 | 8,050,000,000 | Yes |

| Transfer type | Final state | Journal records |
| --- | --- | --- |
| NATIONAL | SETTLED | 4 |
| INTERNATIONAL | SETTLED | 4 |
| INTERNATIONAL | RETURNED | 6 |

### Escrow evidence

One exported escrow, local contract-call records and one audit anchor are present. The simulated chain reports ready=true and the anchor comparison reports PASS. The runtime engine is py-evm, an in-memory EVM with no peers, no public network and no real tokens. [E04]

> **Invariant vs economic truth** — Balanced books can faithfully record incorrect or invented transactions. These results do not validate actual rail limits, fees, currency liquidity, settlement finality or a production contract deployment. The local chain also shares the database-owner trust boundary explained in section 07.

## AI behavior: evidence without overclaim
*09 / FRESH LOAD CHECK + SUPPLIED BENCHMARKS*

### Fresh component loading

Reader, DialoguePolicy, RiskScorer and LocalExplainerLLM loaded in the current environment. The live API run used the shipped local components, with the operator cloud path disabled. This confirms loadability and participation in a finite demonstration—not a newly trained model or a new accuracy/safety study. [E06]

| Supplied evaluation | Recorded value | Required interpretation |
| --- | --- | --- |
| NLU blind routing | 100/113; 88.50% | Frozen holdout reproduced previously; not a new independent blind study. |
| NLU attack blocking | Blind 13/14; hard 18/20 | Finite corpus; misses remain. Authorization must not depend on filter perfection. |
| Hard-set action start error | 2.47% (reported rate) | Planning/action-start metric, not unauthorized financial settlement. |
| Raw dialogue policy | 50 wrong plans / 6,000 | Before runtime review; compare fairly with safer conservative baseline. |
| Ask-all-and-confirm baseline | 1 wrong plan / 6,000 | The learned policy is not safer than this baseline in the supplied simulator. |
| Risk desk medium/high routing | Precision 29.22%; recall 56.48% | Synthetic data; review routing, not a real fraud detector. |
| Explainer output acceptance | 80.86% over 700 pairs | Guarded rewrites can fall back; not a factual-correctness guarantee. |

> **Do not promote benchmarks into approval authority** — These are supplied benchmark JSON values, not reruns for this report. No representative corridor/user validation, bias study or live cloud-provider test was conducted. Deterministic controls and human approval are evaluated separately. [H03; C07–C08]

## Historical evidence & reconciliation
*10 / SUPPLIED — NOT RERUN*

| Supplied artifact | Recorded result | Scope caveat |
| --- | --- | --- |
| release/backend.xml | 1,542 cases; no failures/errors | Earlier run; final focused regressions overlap. |
| release/backend-final-regression.xml | 42 cases; no failures/errors | Focused wording/review checks; not an extra independent full suite. |
| release/packaging-recheck.xml | 53 cases; no failures/errors | Packaging/preflight scope. |
| release/web-tests.log | 439 web unit/component cases | Supplied release log; older summary says 463. Not rerun. |
| release/browser-tests.log | 24 browser smoke tests | Production static UI with API fixtures mocked; not a live bank test. |
| security_2026-10-18/ | 146/146 attacks; 8/8 abuse; 42/42 assistant; 14 MITM defended; 48/48 browser | Team-authored historical probes; no independent pentest. |
| release/demo-recording.json | 5/5 scenes; 95-second actual local UI/API recording | Not the complete MFA-to-settlement lifecycle; not newly recorded here. |
| Docker and telemetry files | Historical Docker/egress records supplied | No fresh Docker runtime or packet capture in this review. |

### Why the counts differ

The archive contains older summaries alongside detailed release records from different runs. A test count is meaningful only with its exact artifact, source snapshot and scope. This report does not silently choose the largest number, combine overlapping runs or call supplied logs fresh. The freshly generated E01 JUnit is the primary current backend result. [H01–H04; E01]

> **Publication history** — The supplied evidence-normalization.json records earlier log formatting and synthetic URL userinfo normalization. Those historical records are retained as supplied; this report does not assert that every inherited artifact was independently regenerated.

## Reproduction procedure
*11 / SAFE REVIEWER RUNBOOK*

### 1. Verify and prepare

Extract the supplied main source in an isolated workspace. Verify its archive SHA-256 against section 02. Create a dedicated virtual environment and install backend/requirements-dev.txt. Dependencies may require platform-specific wheels; a clean install remains the reviewer’s task. Use only synthetic data.

```text
cd StudyRoute-main/backend
python -m venv .venv
# Activate the virtual environment for your operating system.
python -m pip install -r requirements-dev.txt
python -m pytest -o addopts='' -q --junitxml=backend-current.xml
```

### 2. Isolated live API

The included tools/run_live.py documents the exact automated sequence used here. Configure a NEW DATA_DIR and DATABASE_URL outside the source tree; use APP_ENV=sandbox, WEBHOOK_BASE_URL=http://127.0.0.1:18763 and all four model modes auto. Remove operator cloud/provider secrets. Seed once, then start the API:

```text
python -m app.scripts.seed --if-empty
python -m uvicorn app.main:create_app --factory \
  --host 127.0.0.1 --port 18763 --no-access-log
```

### 3. Export and verify — separate terminal, same environment

```text
python -m app.scripts.export_evidence \
  --base-url http://127.0.0.1:18763 \
  --out /path/to/new-evidence --tamper
# From project root:
python scripts/scan_repo.py
```

> **Destructive-test warning** — The --tamper option deliberately changes an audit record and restores it. It is only for disposable local data. Do not reuse a deployed database or run --reset against a deployment volume. Stop the local API after collection. Included helper scripts use this review workspace’s absolute paths; adapt them before reuse.

## Evidence index & acceptance boundary
*12 / REVIEWER HANDOFF*

| ID | Files / purpose |
| --- | --- |
| E01 | Fresh complete backend regression — validation/backend-current.log; validation/backend-current.xml; validation/backend-current.exit |
| E02 | Fresh real local API demonstration — validation/live-run.json; validation/live-export.log; validation/live-evidence/sandbox_operation_log.txt |
| E03 | Fresh audit and tamper evidence — validation/live-evidence/audit_log.json; audit_verify.json; tamper_demo.json (same directory) |
| E04 | Fresh financial and escrow evidence — validation/live-evidence/payments.json; bank_network.json; smart_escrow.json |
| E05 | Provenance and independent chain recomputation — validation/source-identity.json; source-file-inventory.json; evidence-integrity-check.json; tools/inspect_evidence.py |
| E06 | Fresh source hygiene and model loading — validation/source-scan.log; validation/environment-models.json; validation/rbac-matrix.json |

### Package contents

- Two reports in PDF, editable DOCX and Markdown; shared EVIDENCE_INDEX.md.
- Fresh validation logs, JUnit XML, local API operation JSON, source inventory, model/runtime metadata and machine-derived RBAC matrix.
- Selected supplied/historical test records, probe outputs and AI evaluation JSON under inherited/; each remains marked as not rerun.
- Reproduction and verification helper scripts; SHA256SUMS.txt for delivered files.

### Acceptance boundary

The package supports inspection of this source archive and reproduction of a synthetic local demonstration. It does not establish a successful public deployment, independent security assurance, real-world model calibration, regulatory approval or competition acceptance. No submission email, repository push or judge-access grant was performed.

> **Recommended reviewer sequence** — Verify file hashes → inspect source identity → read E01/E02 raw outcomes → compare E03 negative tamper result → inspect E04 ledger invariants → review the companion risk register before considering any wider deployment.

