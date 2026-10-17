# Deck outline (blueprint 19.2) as slide text

Twelve slides for the judges, built as `StudyRoute_Deck.pptx` (generator: `deck/build_deck.js`). The
rules cap the final presentation at **10 minutes**. The speaker notes in the file are about **8.9
minutes** of speech at a brisk 160 words a minute (a calmer 140 is just under 10), so keep any
live demo to **1 minute** or none and point to the recorded video (`VIDEO_SCRIPT.md` is its scene
list, 4:50). Rehearse with a timer and trim a note if you run over. Screenshots come from the running app; they are
in `submission/screenshots/`, or take fresh ones after `docker compose up --build`.
Keep every figure synthetic and keep the sandbox banner visible in each screenshot.

## 1. StudyRoute
- Cross-border and Student Finance Assistant (Topic C). Team: TeamEkxin.
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
- StudyRoute simulates the chain with invented banks, a correspondent and a double-entry ledger (screen: Bank network; guide: `docs/BANK_NETWORK.md`).

## 5. Solution overview
- **Agent task:** one sentence in the chat becomes a quote, a ranking, a deadline plan and a draft proposal; the human still creates the draft and approves.
- Compare, plan, checklist, KYC gate, safe approval, tracker, compliance report, audit log.
- Screenshot: the plan card in the chat (`17-agent-plan.png`).

## 6. The engine
- True total cost = FX margin + fixed fee + SWIFT fee + sender-paid fees + shortfall.
- Worked example (synthetic, GBP 10,000, mid rate 160.00): B 1.58%, C 1.63% with a GBP 35 shortfall, A 2.16%.
- Integer minor units and `Decimal` rates; no floats.
- Smart send plan: the same GBP 12,000 costs BDT 68,400 sent monthly and BDT 28,500 sent at once, because fixed fees are paid on every transfer.
- Student guide: which of 20 student cities a monthly budget in taka covers, and the steps for the first weeks abroad. Invented figures, marked not verified. One-click "create draft and request approval"; approval still needs MFA.
- Deadline fit: the cheapest provider that ARRIVES before the due date (both countries' working days); if the cheapest would be late, the plan says so. Currency-drop stress test: the same quote priced again if the taka weakens 5, 10, 15 or 20%, a what-if on synthetic rates and not a forecast.

## 7. Proven, and not proven yet
- Proven by tests and logs: every number comes from one engine in integer money (all 24 scenarios mapped to tests); only a human with a fresh MFA code can approve, and the AI has no such permission; edit one audit row and Verify fails at that event; the stack starts from the zipped archive with docker compose (run for real on 15 and 17 October).
- Not proven, and said so: rates, fees and city costs are invented and not yet compared with real quotes; no real parent has used it and the trained models saw synthetic data; no outside security review; Bangladesh Bank limits are placeholders marked Not verified.
- Both lists are in the repository: `docs/OPEN_QUESTIONS.md` and `docs/SECURITY_SELF_ASSESSMENT.md`.
- Smart escrow and the bank network are extras beyond Topic C. They are not slides; they get one sentence on slide 12 and a few seconds in the video. Screenshots stay in `submission/screenshots/` (`27-smart-escrow.png`, `29-escrow-schedule.png`).

## 8. AI that cannot cheat
- Pipeline: policy check, facts from the engine, masking, model (optional), number guard, tool guard, audit.
- The number guard blocks any figure the engine did not produce. Template mode works with no key.
- The AI proposes; it may make a quote, but it has no approve, submit, cancel, limit or config tool and cannot create a payment.

## 9. A trained agent, measured
- A small language model (bge-small-en-v1.5, fine-tuned on a GPU in a few minutes) reads what a parent types: the intent and the exact words that carry an amount, a currency or a date. It proposes; plain code checks; the engine calculates.
- On 113 messages written by hand after the model was frozen (scored once): right intent 88.5% against 61.1% for the old rules, a plan request read completely and exactly 100% against 57.6%, attacks blocked 92.9% against 28.6%. On real bank questions: 95% against 40%.
- Reinforcement learning: a small policy trained with Double DQN decides when to ask, read back or plan. On simulated parents, wrong plans 0.8% against 2.8% for the old behaviour, 1.17 questions against 0.44. Plain code limits its legal moves; it never approves or moves money.
- Honest limits on the slide: synthetic data, English, no real users, about plus or minus 7 points, about 1 attack in 14 still slips past it, and the simulated parents and rewards are our assumptions.
- Numbers come from `ml/evaluate.py` (`docs/AI_EVALUATION.md`) and `ml/rl/evaluate_rl.py` (`docs/AI_RL_EVALUATION.md`); the designs are in `docs/AI_AGENT.md` and `docs/AI_RL.md`.

## 10. Security and compliance
- Threat and control matrix with a proof for every row (`docs/SECURITY.md`).
- KYC gate, MFA-bound approval tied to a summary hash, idempotency, HMAC webhooks, rate limits, CSP.
- Audit chain: Verify PASS, then Verify FAIL after an edit; the head of the chain is anchored on the simulated chain. Each payment has a compliance report whose hash the browser verifies.

## 11. Sandbox honesty
- Synthetic data everywhere, labelled on every screen.
- Rules in config with source, last checked and a verified flag; yellow "Not verified" badges.
- "Indicative. Confirm with your AD bank." Never "this is legal".

## 12. Impact and next steps
- More corridors and a verified rule set; moon-dependent holidays.
- A real AD bank partnership for quotes and KYC.
- Escrow already runs in the sandbox; next, a permissioned chain with a bank-issued deposit token.
- Regulator reporting built on the compliance report. Credit building (named in Topic C, not built).

## Demo order (3 to 5 minutes)
Follow blueprint 19.1 or run `python -m app.scripts.demo_flow` first to rehearse. Keep the security
moment (replay, forged webhook, prompt injection, Verify PASS then FAIL) for the end.
