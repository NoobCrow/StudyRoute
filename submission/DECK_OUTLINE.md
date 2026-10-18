# Deck outline as slide text

Twenty-one slides for the judges, built as `StudyRoute_Deck.pptx` (generator: `deck/build_deck.js`). The rules cap
the final presentation at **10 minutes**. The speaker notes in the file are about **8.7 minutes** of speech at a
normal 150 words a minute (about 10 at a slow 130), which is about half a minute a slide, so keep any live demo
to nothing and point to the live site and the video (`VIDEO_SCRIPT.md` is its scene list). The notes are also in
`StudyRoute_Deck_Speaker_Notes.txt` with a time for each slide and an anticipated Q&A page that is not read aloud.
`python scripts/preflight.py` fails if the notes ever run past 10 minutes at 150 words a minute. Rehearse with a
timer and trim a note if you run over.

Pictures marked **live** are screenshots of the public deployment (https://studyroute.bot-keep.xyz) taken on
19 Oct 2026 and kept in `submission/screenshots/live/`. Everything shown is synthetic and the sandbox banner is
visible in each screenshot.

| # | Slide | What it shows |
|--:|-------|---------------|
| 1 | StudyRoute | Topic C; "the engine calculates, the AI explains, the human approves, and every step is logged"; sandbox, synthetic data. Live pictures of the student guide, bank network and smart escrow. Team: TeamEkxin |
| 2 | The posted fee is not the price | The hidden exchange-rate margin is 63% of the real cost in the worked example; fees on the way; short payment; two calendars; paperwork |
| 3 | A family carries the risk | The parent who pays in BDT and the student who needs the university paid on time; one plan for both |
| 4 | How money really moves | Parent, AD bank, correspondent bank, receiving bank, university; where each step fails; simulated with invented banks |
| 5 | From question to settled payment | One sentence becomes a plan card; the agent does the steps, a person decides and approves with a fresh MFA code |
| 6 | Live: comparing providers | **Live** quotes for GBP 10,000: B 1.58%, C 1.63% (GBP 35 short), A 2.16%, with a bar graph of the true total cost |
| 7 | The engine does the maths | Integer-money cost formula, the three providers, the smart send plan, where Provider B's BDT 25,300 goes |
| 8 | Live: one sentence, read back | **Live** assistant panel (mandatory read-back) and **live** deadline planner; the assistant cannot approve |
| 9 | An AI that cannot cheat | The seven-step pipeline; only the optional model is not deterministic; number guard and tool guard |
| 10 | Trained agents, measured | The reader against the old rules on 113 frozen messages; the dialogue policy; the explainer and risk router and their limits |
| 11 | Models against baselines | Graphs: reader against rules, router top-1% against random, dialogue policy wrong plans before and after |
| 12 | Risk score, human decision | The AI risk score (0 to 100) from four factors, the warning, the bank reviewer's yes, ask for more or no with MFA; it never approves. Local sandbox screenshots |
| 13 | Proven, and not proven yet | What the tests and logs show, and the plain list of what they do not |
| 14 | Every test we ran | 1,679 backend, 463 web, 24 browser tests, 24 of 24 scenarios, 314 security probe records, and **live** GitHub CI with all six jobs green |
| 15 | Security you can verify | Permission tiers; **live** audit log with Verify giving PASS; the tamper test |
| 16 | Attacking our own app | Graph of the 314 recorded checks by tool; the man-in-the-middle test: what held and what did not |
| 17 | Security problems we found | Seven problems with their status (mitigated, open, fixed, partly), including plain HTTP and the stolen-token risk |
| 18 | Honest by design | Banner and header on every response, the "Not verified" badge, the sealed compliance report |
| 19 | Why it can work | USD 881.7m sent for overseas education in FY2025-26, the sums, who gains, and that there is no partner, pilot or user yet |
| 20 | What the brief asked | The requirements table with status, and which slides show each scoring criterion |
| 21 | What comes next | Verified rules, an AD bank partner, credit building (not built), a real chain; team and repository link |

Sources and sums for slide 19: `docs/BUSINESS_CASE.md`. Figures on slides 10 to 12 come from
`submission/evidence/ai_evaluation.json`, `ai_rl_evaluation.json`, `ai_explainer_evaluation.json` and
`ai_risk_training.json`; the security figures on slides 16 and 17 from `submission/evidence/security_2026-10-18/`
and the security self-assessment, sections 13 and 14.
