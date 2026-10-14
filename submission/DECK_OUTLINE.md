# Deck outline (blueprint 19.2) as slide text

Ten slides for the judges. Screenshots come from the running app; capture them from
`submission/screenshots/` or take fresh ones after `docker compose up --build`.
Keep every figure synthetic and keep the sandbox banner visible in each screenshot.

## 1. StudyRoute
- Cross-border and Student Finance Assistant (Topic C). Team: [team name].
- "The engine calculates, the AI explains, the human approves, and every step is logged."
- Sandbox: synthetic data, no real money moves.

## 2. The problem
- Hidden exchange-rate margin that hides the real price.
- Fees taken on the way: correspondent and receiving banks.
- Tuition that arrives short, so the university adds a late fee or cannot match it.
- Missed deadlines (Bangladesh weekend is Friday and Saturday; the host country has its own days).
- Weeks of paperwork with an unclear list of documents.

## 3. Who it helps
- The parent in Bangladesh who pays in BDT and carries the risk.
- The student abroad who needs the university paid on time.
- Real pain points: unclear rules, surprise fees, repeated bank visits.

## 4. How money really moves
- Parent (BDT) to AD bank, which sells foreign currency and sends a SWIFT message with a UETR and a charge code.
- Correspondent bank may deduct a lifting fee; the receiving bank may deduct a fee; the university matches by reference.
- Diagram: blueprint section 3. SWIFT carries the instruction; banks settle between their accounts.

## 5. Solution overview
- Compare, plan, checklist, KYC gate, safe approval, tracker, audit log, explainer chat.
- Screenshots: Compare, Payment (summary and tracker), Documents, Audit log, Chat.

## 6. The engine
- True total cost = FX margin + fixed fee + SWIFT fee + sender-paid fees + shortfall.
- Worked example (synthetic, GBP 10,000, mid rate 160.00): B 1.58%, C 1.63% with a GBP 35 shortfall, A 2.16%.
- Integer minor units and `Decimal` rates; no floats.

## 7. AI that cannot cheat
- Pipeline: policy check, facts from the engine, masking, model (optional), number guard, tool guard, audit.
- The number guard blocks any figure the engine did not produce. Template mode works with no key.
- The AI proposes; it has no approve, submit, cancel, limit or config tool.

## 8. Security and compliance
- Threat and control matrix with a proof for every row (`docs/SECURITY.md`).
- KYC gate, MFA-bound approval tied to a summary hash, idempotency, HMAC webhooks, rate limits, CSP.
- Audit chain: Verify PASS, then Verify FAIL after an edit.

## 9. Sandbox honesty
- Synthetic data everywhere, labelled on every screen.
- Rules in config with source, last checked and a verified flag; yellow "Not verified" badges.
- "Indicative. Confirm with your AD bank." Never "this is legal".

## 10. Impact and next steps
- More corridors and a verified rule set; moon-dependent holidays.
- A real AD bank partnership for quotes and KYC.
- Regulator-ready reporting from the audit log.

## Demo order (3 to 5 minutes)
Follow blueprint 19.1 or run `python -m app.scripts.demo_flow` first to rehearse. Keep the security
moment (replay, forged webhook, prompt injection, Verify PASS then FAIL) for the end.
