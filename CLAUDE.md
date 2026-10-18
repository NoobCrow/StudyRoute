# CLAUDE.md - StudyRoute

## What this project is
StudyRoute is a SANDBOX AI assistant for the FinTechathon 2026 International Track,
Topic C (Cross-border and Student Finance Assistant). Corridor: a parent in
Bangladesh (BDT) paying tuition and living costs for a student abroad.
No real money moves. All data is synthetic. Every screen shows a sandbox banner.

Source of truth for requirements: docs/BLUEPRINT.md (sections 1 to 16 and 22).
If code and the blueprint disagree, stop and ask, or update the blueprint.

## Hard deadline
Submission closes 20 Oct 2026, 23:59 Beijing time (21:59 Dhaka).
Internal target: submit by the evening of 19 Oct. Prefer simple and working
over clever and unfinished.

## Golden rules (never break)
1. The deterministic engine computes every number. The LLM only explains.
2. The AI can never approve, submit, cancel, or change limits or config.
   Only a human user with a fresh MFA proof can approve.
3. Money is integer minor units plus a currency code. Never floats.
4. Every state change writes one audit event in the same DB transaction.
   The audit log is append-only and hash-chained (SHA-256, see blueprint 15).
5. Every payment-creating POST needs an Idempotency-Key.
6. No secrets, real IDs, passports or real account numbers in code, logs,
   tests, prompts or git. Use .env (gitignored) and .env.example.
7. Mask personal data before any text goes to an LLM.
8. Rules and limits live in config with source_url and verified flag.
   Never state something is "legal" or "within the limit". Say:
   "Indicative. Confirm with your AD bank."
9. Label simulated things as simulated. Never claim a live bank or live FX feed.

## Stack (change only with a good reason)
- Backend: Python 3.12, FastAPI, SQLAlchemy, SQLite (Postgres optional), pytest
- Frontend: Next.js (static export), React and TypeScript, Tailwind and shadcn/ui, in web/
- One-command start: docker compose up
- AI: provider-agnostic client in backend/app/ai/. Must run in TEMPLATE MODE
  with no API key. Pin and log the model version when a key is present.
- The trained reader (backend/app/ai/nlu/) only PROPOSES: it marks words, plain code
  turns them into values, the engine calculates. NLU_MODE=off must keep working.

## Layout
backend/app/engine/     money, fx, quote, ranking, planner (pure, no I/O)
backend/app/domain/     state machine, kyc, limits, recipients validation
backend/app/api/        routes, auth, idempotency, errors (RFC 7807)
backend/app/audit/      hash chain, verify
backend/app/providers/  mock provider adapters, signed webhooks
backend/app/ai/         orchestrator, masking, number guard, tools
backend/app/ai/nlu/     the trained reader (tokenizer, ONNX runtime, value checks); model in model/
backend/app/ai/dialogue/ the RL dialogue policy: state, legal-action rules, NumPy policy; weights in model/
backend/app/ai/explainer/ the small trained explainer: rewords the engine's draft; every rewrite is checked in code; model in model/
backend/app/ai/risk/    the small trained risk model that rates each payment and routes it to a person; never clears or approves
backend/app/domain/bank_review.py  the sandbox bank's review desk (docs/BANK_REVIEW.md)
ml/                     training and evaluation of the reader; ml/rl/ the RL simulator and trainer
ml/explainer/           data, teacher, verifier, training and evaluation of the explainer (docs/AI_EXPLAINER.md)
ml/aml/                 data build, training, ablation and operating points of the risk model (docs/AI_RISK.md)
backend/tests/          pytest. One test per blueprint test ID (T01..T24)
web/                    screens: dashboard, compare, payments, recipients, documents,
                        audit, rules, bank network, smart escrow, sandbox, assistant
docs/BLUEPRINT.md       the spec
config/rules.yaml       limits, checklists, calendars (blueprint 13)

## Commands
- Run tests: cd backend && pytest -q
- Lint/format: ruff check . && ruff format .
- Web UI checks: cd web && npm run typecheck && npm run lint && npm test; npm run build; npm run e2e
- Start all: docker compose up --build
- Reset demo data: python -m app.scripts.seed
- Run the demo script against a running API: python -m app.scripts.demo_flow
- Show the AI risk model and the bank review desk against a running API: python -m app.scripts.review_demo
- Check the AI layer (template mode or a configured model): python -m app.scripts.check_ai
- Regenerate the destination countries (needs `pip install babel`, a dev tool only): python scripts/gen_countries.py
- Scan for secrets, real e-mails and TODOs: python scripts/scan_repo.py
- Attack the running app (lab only; see scripts/security/README.md): scripts/security/attack_probe.py, brute_probe.py, browser_audit.mjs
- Re-measure the trained reader against the rules: python ml/evaluate.py (backend venv)
- Retrain the reader on a GPU: docs/AI_AGENT.md section 7
- Retrain / re-evaluate the RL dialogue policy: docs/AI_RL.md section 8 (ml/rl/)
- Retake the README screenshots (fresh demo data, API and built web UI running): python -m app.scripts.gallery
- Build the submission archive: python scripts/make_submission.py
- Make the send-ready PDFs with cover pages (pip install markdown, needs Chrome): python scripts/make_pdfs.py
- Rebuild the deck (always with the team values): cd submission/deck && TEAM_NAME="TeamEkxin" REPO_LINK="https://github.com/NoobCrow/StudyRoute" node build_deck.js

## How to work
- Work one blueprint phase at a time. Read the relevant section first.
- Write tests first for engine, state machine, idempotency, HMAC and audit.
- Run the tests before you say a task is done. Show the output.
- Keep functions small. Type everything. No dead code, no TODO left silently.
- Prefer boring, standard libraries. Do not write your own crypto.
- When unsure about a rule or number, add it to config as verified: false
  and list it in docs/OPEN_QUESTIONS.md instead of guessing.
- Commit small, with clear messages, after tests pass.

## Definition of done (MVP)
Blueprint tests T01 to T24 pass, docker compose up works from a clean clone,
the demo script in blueprint 19 runs end to end, every screen has the sandbox
banner, and README explains setup, demo accounts and the security design.
