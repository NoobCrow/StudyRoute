# Execution evidence (index)

Everything here is **synthetic**: simulated accounts, providers and settlement. No real money moved and no real
data is used. Each file below was produced by the command or the run named beside it. Where a file is recorded by
hand or by a separate tool, the table says so and says **this command does not regenerate it**. Every file has a
SHA-256 in [SHA256SUMS.txt](SHA256SUMS.txt); check them with `sha256sum -c SHA256SUMS.txt` from this folder.

The Execution Evidence Report ([StudyRoute_Execution_Evidence_Report.pdf](../StudyRoute_Execution_Evidence_Report.pdf))
reads these files and says what each one proves and what it does not.

## A. The sandbox run

| File | What it shows |
|------|---------------|
| `sandbox_operation_log.txt` | The 14-step demo run against the API, one line per check, OK or FAIL |
| `audit_log.json` | Every audit event in order, each with `prev_event_hash` and `this_event_hash` |
| `audit_verify.json` | The hash-chain verification: status, events checked, head hash |
| `tamper_demo.json` | Verify after one audit row was edited behind the application's back (FAIL at that sequence), and after it was restored (PASS). Only present when run with `--tamper` |
| `payments.json` | The payments created, with their state timeline and UETR |
| `bank_network.json` | The simulated interbank transfers (national and international) with every hop, the simulated messages and the double-entry journals, plus the trial balance and mirror-account check |
| `smart_escrow.json` | The smart escrows (schedule, state, the contract call log with its hashes), the simulated chain's status, the audit anchors written to it and the check that the database still matches the chain |
| `review_demo_run.txt` | The AI risk score and the bank review desk, the output of `python -m app.scripts.review_demo` (the other files in A are written by the export command) |

To reproduce A: start the API with fresh demo data, then run `python -m app.scripts.export_evidence --tamper` from `backend/`.

## B. Runs of 18 October 2026 (Docker and the security tools)

| File or folder | What it shows |
|----------------|---------------|
| `docker_2026-10-18/` | The raw output of the Docker run (Ubuntu 24.04 VM, Docker 29.1.3): smoke, the 14-step demo before the fix (3 failed checks, kept on purpose) and after it (66 OK lines), the AI risk and bank review demo, the real-Chrome audit (48 of 48) and the hardened overlay |
| `security_2026-10-18/` | The raw output of the six security tools against throwaway lab databases and the current code: `attack_probe.txt` (146 of 146 defended, including the bank review desk), `brute_probe.txt` (8 of 8), `leak_scan.txt` (all clear, 50 checks), `mitm_probe.txt` (14 defended, 0 failed), `assistant_probe.txt` (42 of 42), `browser_audit.txt` (48 of 48 in real Chrome under the production CSP). Written by `scripts/security/`; see [docs/SECURITY_TESTING.md](../../docs/SECURITY_TESTING.md) |
| `docker_run.txt` | The notes of that Docker run (container health, the read-only and capability-dropped settings, what failed, why and what was changed). Recorded by hand; **this command does not regenerate it** |
| `docker_telemetry_capture.txt` | A packet capture of the real backend container: ONNX Runtime's Microsoft telemetry was found phoning home, switched off, and re-checked (0 packets to a public address, with the demo and 130 s idle). Recorded by hand; **this command does not regenerate it** |

## C. The trained components

| File | What it shows | Written by |
|------|---------------|------------|
| `ai_evaluation.json` | The reader against the rule-based reader on held-out, natural and blind data: routing, values, attacks blocked, harmless blocked, latency (readable version: [docs/AI_EVALUATION.md](../../docs/AI_EVALUATION.md)) | `ml/evaluate.py` |
| `ai_backbone_ablation.json` | The six base models that were fine-tuned and compared on the dev split | `ml/collect_ablation.py` |
| `ai_rl_evaluation.json` | The dialogue policy against the old behaviour and the hand-written rules on simulated conversations, with the reward-sensitivity runs and the SHA-256 of the policy ([docs/AI_RL_EVALUATION.md](../../docs/AI_RL_EVALUATION.md)) | `ml/rl/evaluate_rl.py` |
| `ai_explainer_evaluation.json` | The explainer on 700 held-out questions: how many answers pass every check, invented figures, figure precision and recall ([docs/AI_EXPLAINER.md](../../docs/AI_EXPLAINER.md)) | `ml/explainer/evaluate.py` |
| `ai_risk_training.json` | The shipped risk network against the baselines on the later test period: average precision and the share of flagged payments found in the top 1% and 5% | `ml/aml/train.py` |
| `ai_risk_model_comparison.json` | The 24 configurations (ten learned models, four rule or random baselines, on 8 or 13 inputs) on the same time split ([docs/AI_RISK_MODELS.md](../../docs/AI_RISK_MODELS.md)) | `ml/aml/compare.py` |
| `ai_risk_operating_points.json` | The routing the review desk uses and the other thresholds: accuracy, precision and recall at each, with the "never flag anything" row ([docs/AI_RISK.md](../../docs/AI_RISK.md)) | `ml/aml/operating_points.py` |
| `ai_risk_ablation.json`, `ai_risk_ablation_first_pass.json` | What removing the channel and currency inputs cost (nothing), and the first pass with them | `ml/aml/ablate.py` |

None of the files in C is regenerated by the export command. They are re-measured by the scripts named.

## D. Provenance and reproduction (`release/`)

| File | What it shows |
|------|---------------|
| `release/demo-recording.json` | The steps, timings and result of the scripted screen recording used for [StudyRoute_Demo.mp4](../StudyRoute_Demo.mp4) (17 October 2026) |
| `release/holdout-recheck.json` | A rerun of the frozen holdouts with the hashes of the code, data and model; "not new evidence of generalisation". Written by `ml/check_reproduction.py` |
| `release/corridor_sources.json` | The public sources behind [docs/CORRIDOR_VALIDATION.md](../../docs/CORRIDOR_VALIDATION.md), and the gaps they leave |

Older test logs from earlier repair releases were removed from this folder on 18 October 2026 so that no stale
count could be mistaken for a current one; they remain in the git history.
