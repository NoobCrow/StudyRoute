# Hardening v2 verification

Generated UTC: 2026-10-17T18:58:39.725105+00:00

This records observed local checks, not an official judging score, independent penetration test,
real-money trial, clean-machine dependency installation or production certification.

| Check | Observed outcome | Scope/evidence |
|---|---|---|
| Complete backend suite | **1558 passed**, 0 failures/errors; 751.86 s | `backend-full.xml`, `backend-full.log`; synthetic in-process API |
| Institution-policy regressions | **16 passed** | `institution.xml`; declarations, invalid types/countries, rename persistence, generic-quote bypass, legacy approval/submit, reset and additive DB creation |
| Frontend components | **440 passed**, 39 files | `vitest.log`; includes explicit institution declaration/reset |
| TypeScript / ESLint / Python ruff / changed frontend formatting | PASS | Corresponding logs |
| Production build | PASS; 17 static pages, 51 inline scripts / 17 CSP hashes | `build.log`; existing CSP lifecycle patches retained, no unsafe-inline relaxation |
| Desktop/mobile browser smoke | **24 passed**, one worker | `playwright-serial.log`; real static UI with **mocked API** |
| Earlier contended browser run | **22 passed, 2 failed** | `playwright-contention.log`; dashboard/quote readiness timeouts during concurrent backend and browser audit; retained, not silently dropped. Later serial full run passed without changing app assertions or timeout thresholds |
| API black-box attack probe | **122/122 defended**, 300 responses | `attack-probe.log`; disposable two-household sandbox |
| Assistant hostile prompts | **42/42 defended** | `assistant-probe.log`; offline template/reader, not a connected cloud LLM |
| Leakage canaries | **ALL CLEAR** for tested sinks | `leak-scan.log`; synthetic planted values, not universal leakage proof |
| Replay/tampering probe | **14 defended, 0 failed, 4 informational** | `mitm-probe.log`; HTTP/token-theft limitations retained |
| Real-browser security audit | **42/42 checks passed** | `browser-audit.log`; stored XSS, CSP, third-party requests, cookies and assets |
| Fresh intent challenge | Agent **54/60**, baseline **51/60**; attack cases 8/8 vs 7/8 | `intent-challenge.json`; AI-authored English synthetic, frozen before first run, no tuning; errors retained |
| New real UI/API recording | **3/3 checked steps**, 0 page/CSP errors; 32.28 s | `route-guard-recording.json`, `../../StudyRoute_Route_Guard.mp4`; no mocked API, only synthetic data |

## Reproduce

With locked dependencies installed, from repository root:

```bash
cd backend
python -m pytest -q
cd ../web
npm run typecheck
npm run lint
npm test
npm run build
CHROME_PATH=/path/to/chromium npm run e2e -- --workers=1
cd ..
python ml/review_challenge.py
python scripts/scan_repo.py
python scripts/make_submission.py
```

Security-lab setup and commands are in `scripts/security/README.md`. Always use a disposable local
sandbox; never probe real household data or public systems. The functional probe lab disables rate
limiting to avoid masking other tests, not as a deployment recommendation.

The new recording script is `scripts/record_route_guard.cjs` (loopback only). Existing v1 video and
release evidence are retained as historical evidence; the v2 route recording specifically verifies
the new code. The inherited PPTX, contracts and model weights were not redesigned or retrained in v2.

## Remaining limitations

- Original credential revocation must be performed at the account/service; not done here.
- Institution declaration/name recognition is not verified account identity and can miss unknown aliases.
- Catalogue covers one reviewed policy. Unknown institutions remain unverified. No Flywire integration.
- No timestamped live bank/Flywire quote, actual financial savings, student/parent study, cloud LLM
  evaluation, clean-machine dependency installation, Docker rerun or GitHub push was performed.
- HTTP is used only on loopback. HTTPS is required remotely; stolen bearer tokens still permit reads
  and draft cancellation until expiry, while payment approval requires separate MFA.
- A curated 60-case routing score is not a competition score or representative financial-task accuracy.
- Source archive integrity, manifest checks and original-credential exclusion are separately checked
  after final packaging; those checks do not revoke secrets or establish the absence of all secrets.

See `docs/HARDENING_V2.md`, `docs/VALIDATION_PROTOCOL.md` and `GITHUB_PUSH_BN.md` before deployment.
