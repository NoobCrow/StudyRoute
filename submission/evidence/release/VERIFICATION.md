# Repair-release verification

Generated UTC: 2026-10-17T18:25:49.119503+00:00

## Observed results

| Check | Actual result | Evidence / scope |
|---|---|---|
| Complete backend suite | **1542 passed**, 98 modules, 603.72 s; exit 0 | `backend.log`, `backend.xml`; in-process API, synthetic banks and data |
| Final financial wording and review regressions | **42 passed**, 22.49 s; exit 0 | `backend-final-regression.log` / XML; run after the final wording edits |
| Packaging / repository / preflight regressions | **53 passed**, 8.15 s | `packaging-recheck.log` / XML |
| Frontend Vitest | **439 passed**, 39 files | `web-tests.log`; component/unit/accessibility tests |
| Production-CSP desktop/mobile browser smoke | **24 passed**, 1.6 min; exit 0 | `browser-tests.log`; production static UI, API responses mocked by existing browser fixtures |
| Production build | PASS, 17 prerendered pages; 51 inline bootstrap scripts, 17 distinct allowed hashes | `web-build.log`; no unsafe-inline relaxation |
| TypeScript / ESLint / Prettier | PASS | `web-typecheck.log`, `web-lint.log`, `web-format.log` |
| Python ruff | PASS; 229 files formatted | `python-style.log` |
| Solidity rebuild | PASS, all 3 artifacts byte-for-byte identical to supplied artifacts | `contracts-build.log`, `contracts-comparison.json`; compiler identifier warning retained |
| Contract dependency install advisory check | 0 reported vulnerabilities | `contracts-install.log`; snapshot, not a security proof |
| Web production dependency advisory check | 0 reported vulnerabilities | `web-production-advisory-audit.json`; excludes development tools |
| Actual local sandbox execution | 14-step flow completes; 75 audit events verify; bank books balance | `sandbox-execution.log`, parent operation JSON; mocked external financial rails, not real bank settlement |
| Actual UI/API recording | 5/5 checked scenes; 0 page/CSP errors; **95.00 seconds** | `demo-recording.json`, `../../StudyRoute_Demo.mp4`; unmocked local backend, synthetic data, English subtitles, no voiceover |
| PPTX preservation audit | PASS, 12 slides, 0 issues | `deck-package-audit.json`; inherited design/theme/object geometry preserved |
| Known original credential exclusion | 7 distinct values from 2 private files: no matches in the source tree checked | `credential-exclusion.json`; values are never stored in the report; account revocation NOT performed |
| Submission preflight | 12 OK, 0 FAIL, 7 OPEN | `preflight.log`; Git/registration/Docker/submission are manual. A source ZIP has no `.git`; use the existing-fork instructions, not a new remote blindly |

Evidence publication: `evidence-normalization.json` records harmless npm version-header normalization
and removal of userinfo from a synthetic rejected-URL test parameter. Test outcomes/counts/times are
unchanged; ANSI terminal colors were stripped. No broad log/XML scanner exemption was added.

The complete backend run was followed by a focused final regression after explanatory charge-code
wording changed. Those regression tests strengthen the warning assertion; they do not relax financial
or authorization checks. An extra final edit only split a long Python string into adjacent literals
for formatting, leaving its runtime text unchanged.

## AI evaluation scope

- The complete six-split NLU evaluation was rerun: `../ai_evaluation.json` and `nlu-reproduction.log`.
  Blind routing is 88.50%, hard routing 91.18%, natural routing 95.15%; blind attack blocking is
  13/14 (92.86%) and hard attack blocking 18/20 (90%). These finite synthetic samples are not
  general security guarantees. A "blind" set reused for reproduction is NOT a new independent study.
- A final blind/hard/natural reproduction has source/data hashes and timestamp in
  `holdout-recheck.json`. The complete earlier run's original hashes are retained unchanged;
  `post-evaluation-changes.json` identifies the subsequent financial-template wording change.
  NLU extractor, weights and datasets were unchanged, and the final holdout results agree.
- `../ai_rl_evaluation.json` and `rl-reproduction.log` rerun 6 baselines, 6000 synthetic conversations
  each. The raw learned policy has 50/6000 wrong plans (0.833%); ask-all-and-confirm has 1/6000
  (0.0167%), not zero. Do not claim the learned policy is safer than that baseline.
- The deterministic API review envelope is covered by regression/API tests and the recording,
  **not** by the raw RL simulator score. Model training, reward ablations and an independent new
  holdout collection were not rerun.
- Shipped ONNX model: 33826615 bytes; SHA-256 `94146e8c4b7292a1ac79365028c7765692a0f8a0aaedd01b85769c82f7fa69c8`.

## Security trust boundary

The checkpoint regression demonstrates: normal PASS → inconsistent audit rewrite FAIL → coordinated
rewrite/rehash of audit and chain logs PASS locally → separately retained trusted-prefix checkpoint
FAIL. Both local logs share SQLite. This is NOT external immutable anchoring. The checkpoint must
be independently protected from the database owner. Exposed credentials must still be revoked by
the account owner; encryption-key rotation must preserve existing encrypted data.

Production browser testing initially exposed unapplied dependency CSP lifecycle patches. Applying
the project's existing `postinstall` patches and rebuilding resolves the violations without weakening
CSP. An initial scanner false positive on a browser-generated video basename was removed by giving
the artifact a stable non-email-like filename; the actual credential rules were not waived.

## Environment and limits

Linux sandbox, Python 3.13.14, Node 24.14.1, ONNX Runtime 1.31.0; local Chromium via `CHROME_PATH`.
Backend/web dependencies were reused from the supplied working environment; contract dependencies
were freshly installed. This does not certify a clean machine, Windows, Docker or remote deployment.
A fresh deployment/CI pass remains the repository owner's responsibility.

No real bank quote, payment-provider authorization, live FX feed, student user study, independent
penetration test, newly audited backend dependency tree, deployed HTTPS or real cloud-provider call
was verified. The real-corridor dossier is partial primary-source research, not live validation.
Development-tool advisories remain documented separately; a zero production advisory result is not
proof of absence of vulnerabilities.

`docker_run.txt`, Docker telemetry capture, model training ablations and older screenshots in the
parent folder are inherited historical evidence, not reruns on this repaired tree. The short video
shows planning and refusal, not the entire MFA-to-settlement lifecycle; operation logs cover that
longer synthetic flow separately. No GitHub push, credential revocation, competition registration,
judge-access grant or submission email was performed. **No 85+/100 score is certified.**

## Reproduce / package

Use `README.md`, `GITHUB_PUSH_BN.md`, `docs/TEST_CASES.md` and the commands alongside each evidence
file. Browser checks: `cd web && npm ci && npm run build && npm run e2e` (Chrome, or `CHROME_PATH`).
Run only disposable demo databases; never delete production volumes to reproduce evidence.
`python scripts/scan_repo.py` must pass before `python scripts/make_submission.py`.
The source ZIP contains `RELEASE_MANIFEST.sha256`; verify hashes after extraction. Dependencies,
private `.env` files, runtime secrets/databases, `.git`, caches and build outputs are intentionally
excluded. The ONNX model, full source, tests, contracts, docs, PPTX, MP4 and evidence are included.
