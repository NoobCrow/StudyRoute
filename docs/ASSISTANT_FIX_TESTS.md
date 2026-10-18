# Assistant fix v2 — validation record

## Reported gaps addressed

- `what can you do?` now gives a concrete capability list, not an ambiguity response.
- `kemon acho?` receives a short Bangla social response.
- Capability/help variants in English, Bangla and Banglish are recognized.
- An immediate repeated greeting gets a short greeting instead of the full introduction.
- `who are you?` has a concise identity answer; offline/model details remain a separate route.
- Whole-message social patterns do not swallow financial instructions or bypass policy checks.

## Validation

Platform: Python 3.13.14, Node.js 24.14.1, Linux, real trained reader enabled in integration
and browser checks. Windows execution was not available; the update uses the existing
working virtual environment and requires no dependency changes.

- V2 conversation regression suite: **104 passed** (v1 had 65).
- V2 complete clean-source backend suite: **1233 passed**.
- V2 real Chromium desktop and mobile: eight distinct replies per viewport through the
  actual frontend and backend. Verified capabilities, repeated greeting, Banglish wellbeing,
  Banglish capability question, factual KYC status, KYC follow-up and concise identity.
  Guard results passed, no task or payment proposal generated, no browser console errors.
- V2 Ruff checks: passed.
- Frontend source is byte-identical to the previously delivered v1 fixed release. That source
  passed Next.js **190 tests**, Vite **140 tests**, TypeScript, Next.js ESLint and production
  build/CSP generation. No frontend dependency, lockfile, model binary or database migration
  changed in v2. Browser checks exercise the same built frontend against the updated backend.
- Final clean source repository scan and ZIP integrity verification: passed.

Existing engine numbers, ownership checks, task continuation, policy refusal, audit,
number guards and human/MFA approval remain in place. History remains an untrusted,
bounded topic hint, never a source of amounts, dates, permissions or action authorization.

## Limitations

This is a bounded offline conversation fix, not a new generative model or a promise of
unrestricted multilingual conversation. Existing external-LLM configuration is unchanged;
no external model service was called. Assistant API mode remains `template` for compatibility,
while the UI labels it `Offline assistant`.

## Reproduction

From `backend/`, with existing requirements installed:

```sh
python -m pytest tests/test_ai_conversation.py -o addopts='' -q
python -m pytest -o addopts='' -q
ruff check app tests/test_ai_conversation.py
```

The real-browser checks use an isolated database and local production-like server, not
any user's database. Runtime state and installed dependencies are not included in the ZIPs.
