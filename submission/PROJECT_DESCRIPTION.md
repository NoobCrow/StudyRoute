# StudyRoute: project description

**FinTechathon 2026, International Track. Topic C: Cross-border and Student Finance Assistant.**
Team: TeamEkxin. Members: Farhan Labib, Md Redwan Hossen, Alim Bin Yeasin and Kalvin Chakma (Ahsanullah University of Science and Technology, Bangladesh). Contact: the e-mail this was sent with.

> StudyRoute is a sandbox. No real money moves, all data is synthetic and every screen says so.
> Guidance is indicative only: confirm with your Authorised Dealer (AD) bank.

## The problem

A parent in Bangladesh who pays a student's tuition and living costs abroad meets unclear rules,
a hidden exchange-rate margin, fees taken on the way, tuition that arrives short, missed deadlines
and weeks of paperwork. Most people compare banks by the posted fee and miss the margin, which is
usually the larger cost.

Topic C asks for solutions to real financial pain points of international students and
cross-border users, such as remittances, tuition payments, credit building and multi-currency
management. StudyRoute covers remittances and tuition payments end to end and shows a household's
money in every currency (simulated accounts); credit building is a next step.

## The solution

StudyRoute is an AI agent that completes this task safely, from first quote to settlement:

- **Compares providers by true total cost.** It ranks each provider by margin, fixed fee, SWIFT
  fee and the correspondent and receiving fees, and warns in red when a university would be paid
  short. In the worked example (GBP 10,000, synthetic rates) it ranks Provider B first at 1.58%,
  C second at 1.63% with a GBP 35 shortfall warning, and A third at 2.16%.
- **Plans the deadline** backwards from the university due date over both countries' working
  days and the bank cut-off, and keeps a document checklist per corridor. Every country is a
  destination; six (UK, US, Germany, Australia, Canada, Malaysia) have their own rules and the
  rest run on clearly labelled generated defaults.
- **Guides a safe approval.** A mock KYC gate, recipient allowlisting, sandbox limits and a
  sanctions check must pass. The parent reads one approval summary with an MT103 preview
  (originator and beneficiary data, charge code, reference), then approves with a fresh MFA code.
  A simulated provider submits, settles and reports back; a tracker shows the UETR and the steps.
- **Does the work from one sentence.** Say "I need to pay GBP 10,000 tuition by 28 October" and the agent reads it, makes the quote, ranks the providers, plans the deadline, checks KYC, recipients and documents, and proposes the draft. It stops at the human gate: it creates no payment and cannot approve. A second task compares sending living costs monthly, quarterly, per term or all at once, because fixed fees are paid on every transfer (in the synthetic example GBP 12,000 costs BDT 28,500 sent at once against BDT 68,400 monthly).
- **Two small trained models, both optional.** A fine-tuned language model reads untidy wording ("ten thousand pounds ... last date end of November"), and a policy trained with reinforcement learning decides when to ask a question, when to read the values back for a "yes" and when to plan. Plain code checks every value and limits the policy's legal moves, so neither model can calculate, approve or move money. Measured results and limits, including that the simulated parents are an assumption: `docs/AI_EVALUATION.md` and `docs/AI_RL_EVALUATION.md`.
- **Helps a student settle, not only pay.** A student guide shows which of 20 student cities a monthly budget in taka covers (rent, food, transport, bills, rounded up in taka by the engine) and lists what to do before flying and in the first weeks. The figures are invented and marked not verified. The draft form can create the draft and request approval in one click; approving still needs the parent and a fresh MFA code.
- **Respects the deadline and tests the downside.** With a due date, the quote names the cheapest provider that arrives in time (counting only days both countries work) and says when the cheapest would be late. A currency-drop stress test prices the same quote again if the taka weakens by 5, 10, 15 or 20 percent. Both come from the fee engine, are read-only, and are labelled as indicative what-ifs on synthetic data.
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
5. **A tamper-evident audit log and a sealed compliance report.** Every state change writes one hash-chained event in the same
   transaction, and the reviewer screen has a Verify button. Edit one row behind the application's
   back and Verify fails at that sequence number. Each payment also has a compliance report (parties,
   ten controls with evidence, approval proof, audit excerpt) whose hash the browser recomputes, so an
   edited copy is detected.
6. **A bank network you can watch.** Invented banks, a clearing house and a correspondent move
   simulated money at home and abroad over a double-entry ledger. A transfer is planned, confirmed by
   a human with an MFA proof bound to that transfer, then passes from bank to bank hop by hop with
   the simulated MT103 and the journals visible. A rejected payment is returned in full, and a
   books-balance check (debits equal credits, every nostro equals its mirror) stays green. The AI has no
   permission to touch it.
7. **Smart escrow on a simulated chain.** For living costs a parent can lock money in a smart contract
   that pays on the dates they choose. The contracts are real Solidity, run in an in-memory EVM
   inside the sandbox; planning locks nothing, locking needs a fresh MFA proof bound to that escrow,
   and a bank reviewer can freeze an escrow with a reason but can never move the funds. Only
   amounts, dates and hashes go on the chain, never a name or an account number. The head of the
   audit hash chain is also checked against the simulated chain. Both histories share SQLite;
   this is a consistency check, not protection against a database owner rewriting both logs. The AI has no permission here. The tokens are not money.

## Security and compliance in the demo

Each control is mapped to a test in `docs/SECURITY.md`: idempotent payment writes (no double
payment), HMAC-signed provider webhooks with replay protection, role-based access with ownership
checks, rate limiting, a strict content security policy, log redaction, and rules held in
configuration with a source and a `verified` flag. Anything not yet checked against an official
Bangladesh Bank source carries a yellow "Not verified" badge and the words "Indicative. Confirm
with your AD bank." The app never claims a live bank or a live FX feed.

## What is built

A FastAPI and SQLite backend (engine, domain, audit, mock providers, AI layer), a Next.js and
TypeScript web app (dashboard, compare, payments, recipients, documents, payment with approval and tracker,
audit log, rules, bank network, smart escrow, assistant), over 1,100 backend tests that trace to all 24 blueprint scenarios (T01 to
T24), over 350 web UI tests (unit, component and automated accessibility checks) plus browser smoke tests, a scripted end-to-end demo (`python -m app.scripts.demo_flow`), CI with
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
