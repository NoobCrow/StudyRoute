# Assistant fix — validation record

Validated on Linux with Python 3.13.14 and Node.js 24.14.1. Windows installation
instructions target the user's existing Python virtual environment and Next.js dev setup;
Windows itself was not available for executing this release.

## Results

- Clean-source backend suite: **1194 passed**, including **65 new conversation regressions**.
- Next.js suite: **190 passed** (single worker for stable accessibility-test timing).
- Legacy Vite suite: **140 passed**.
- Next.js assistant-specific suite: **14 passed**.
- Legacy assistant/task-specific suite: **12 passed**.
- Python Ruff checks, frontend TypeScript checks and Next.js ESLint: passed.
- Next.js production build and CSP hash generation: passed.
- Real headless Chromium browser, desktop and mobile: passed. Each viewport submitted
  eight questions through the UI to the real backend with the actual trained reader.
  All returned distinct, rendered replies; bounded previous-user-message serialization
  was verified; all output guards passed; no task or payment proposal was generated;
  no browser console errors were observed.
- Existing engine comparison regression still returns verified quote figures and fact IDs.
- Final source archive checked with the project's repository scanner; runtime data,
  environments, dependencies and generated builds excluded.

## Scope and limitations

This is a deterministic offline conversation/routing fix, not a newly trained generative
model. Existing NLU and dialogue model binaries are unchanged. API response mode remains
`template` for compatibility; the UI accurately labels it `Offline assistant`.
Existing task confirmation, ownership checks, number guards, policy refusal, audit and
human/MFA approval are preserved. External LLM mode remains available through the existing
configuration, but no external provider was called during this validation.

An initial parallel build did not complete under memory pressure. The final build was
rerun and completed including static export and CSP hashes; only that completed run is
reported as passing. No dependency audit auto-fixes or unrelated dashboard/auth changes
were included.

## Reproduction

From `backend/`, with project requirements installed:

```sh
python -m pytest -o addopts='' -q
ruff check app tests/test_ai_conversation.py
```

From `web/`:

```sh
npm run typecheck
npm run lint
npm test -- --maxWorkers=1
npm run build
```

From `frontend/`:

```sh
npm run typecheck
npm test
```

The real-browser smoke check was run against an isolated seeded database and a local
production-like static server using the generated CSP. Those runtime databases and
installed test tools are deliberately not included in either ZIP.
