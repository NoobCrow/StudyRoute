# StudyRoute: project description

**FinTechathon 2026, International Track. Topic C: Cross-border and Student Finance Assistant.**
Team: [team name]. Members: [names and universities]. Contact: [team leader's e-mail].

> StudyRoute is a sandbox. No real money moves, all data is synthetic and every screen says so.
> Guidance is indicative only: confirm with your Authorised Dealer (AD) bank.

## The problem

A parent in Bangladesh who pays a student's tuition and living costs abroad meets unclear rules,
a hidden exchange-rate margin, fees taken on the way, tuition that arrives short, missed deadlines
and weeks of paperwork. Most people compare banks by the posted fee and miss the margin, which is
usually the larger cost.

## The solution

StudyRoute is an AI agent that completes this task safely, from first quote to settlement:

- **Compares providers by true total cost.** It ranks each provider by margin, fixed fee, SWIFT
  fee and the correspondent and receiving fees, and warns in red when a university would be paid
  short. In the worked example (GBP 10,000, synthetic rates) it ranks Provider B first at 1.58%,
  C second at 1.63% with a GBP 35 shortfall warning, and A third at 2.16%.
- **Plans the deadline** backwards from the university due date over both countries' working
  days and the bank cut-off, and keeps a document checklist per corridor (UK, US, Germany,
  Australia, Canada, Malaysia).
- **Guides a safe approval.** A mock KYC gate, recipient allowlisting, sandbox limits and a
  sanctions check must pass. The parent reads one approval summary with an MT103 preview
  (originator and beneficiary data, charge code, reference), then approves with a fresh MFA code.
  A simulated provider submits, settles and reports back; a tracker shows the UETR and the steps.
- **Explains in plain language.** The chat answers "why is B cheaper than A?" using only numbers
  the engine produced, and lists the facts it used.

## Why the AI can be trusted: the agent design

> The engine calculates, the AI explains, the human approves, and every step is logged.

1. **A deterministic engine computes every number**, with integer minor units and `Decimal`
   rates, never floats. The model never calculates.
2. **A number guard** compares each figure in an answer with the facts it cites. A mismatch is
   discarded and replaced by a template answer. The assistant also works with no model key at all
   ("template mode"), so the demo never depends on a network.
3. **The AI cannot act.** Its tools are limited to reading quotes, plans and checklists and to
   *proposing* a draft or an approval request. It has no way to approve, submit, cancel, change a
   limit or edit a rule; the approve path returns `AI_CANNOT_APPROVE` to its token and logs it.
   Only a human parent with a fresh MFA proof can approve, bound to the hash of the summary seen.
4. **Prompt-injection and privacy controls.** Messages and uploaded text are treated as data and
   checked by a policy filter. Names, accounts, passports, e-mails and phones are masked before
   anything reaches a model.
5. **A tamper-evident audit log.** Every state change writes one hash-chained event in the same
   transaction, and the reviewer screen has a Verify button. Edit one row behind the application's
   back and Verify fails at that sequence number.

## Security and compliance in the demo

Each control is mapped to a test in `docs/SECURITY.md`: idempotent payment writes (no double
payment), HMAC-signed provider webhooks with replay protection, role-based access with ownership
checks, rate limiting, a strict content security policy, log redaction, and rules held in
configuration with a source and a `verified` flag. Anything not yet checked against an official
Bangladesh Bank source carries a yellow "Not verified" badge and the words "Indicative. Confirm
with your AD bank." The app never claims a live bank or a live FX feed.

## What is built

A FastAPI and SQLite backend (engine, domain, audit, mock providers, AI layer), a React and
TypeScript web app (dashboard, compare, recipients, documents, payment with approval and tracker,
audit log, rules, chat), over 440 backend tests that trace to all 24 blueprint scenarios (T01 to
T24), 46 frontend tests, a scripted end-to-end demo (`python -m app.scripts.demo_flow`), CI with
secret scanning, and a one-command start: `docker compose up --build`, then open
`http://localhost:8080`.

## Honest scope

Everything financial is simulated. Login is password plus short-lived tokens with rotation and a
documented sandbox MFA code, not a full external identity-provider flow. The compose stack serves
plain HTTP. Regulatory figures are placeholders until verified. The full list is in
`docs/OPEN_QUESTIONS.md`.

## Impact and next steps

Bangladesh sends many students abroad and every family faces this process. Next: a partnership
with an AD bank for real quotes and a real KYC flow, regulator-ready reporting, more corridors and
the verified rule set, and moon-dependent holidays in the planner.
