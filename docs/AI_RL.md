# Reinforcement learning: when to ask, when to confirm, when to plan

> Repair-release scope: these figures describe the raw model in the synthetic simulator. The API
> now enforces clarification and read-back before planning; its user cost and accuracy have NOT
> been measured in a real-user study. Do not claim these raw-model figures measure the safety envelope.

The trained reader ([AI_AGENT.md](AI_AGENT.md)) tells the assistant what a parent wants and which
words carry an amount, a date or a period. What it should do next is a separate question, and it is
a sequential decision with a real trade-off: every question costs the parent time, but a wrong
quote on screen costs more. This page describes the small policy, **trained with reinforcement
learning**, that makes that choice, what it is allowed to do, how it was trained, and how well it
works. The numbers are in [AI_RL_EVALUATION.md](AI_RL_EVALUATION.md), generated from the shipped file.

The rule that has not changed: **the engine calculates, the AI explains, the human approves, and
every step is logged.** None of the policy's actions moves money.

## 1. The decision

When a message starts a payment plan, the assistant takes one of five actions:

| Action | What the parent sees |
|--------|----------------------|
| `ASK_AMOUNT` | "I still need an amount and a currency." |
| `ASK_DATE` | "I still need the date the university needs it by (or say "no deadline")." |
| `ASK_MONTHS` | "I still need how many months it has to cover." (send plans) |
| `CONFIRM` | "Before I plan it, please check what I understood: GBP 10,000.00 for tuition, due 28 October 2026. Say yes to go ahead, or tell me what to change." |
| `RUN` | the plan card (a quote, a ranking and a deadline plan; a human creates the draft and approves it) |

Before this, the assistant planned as soon as the amount was known and never asked for a missing
date. Whether to ask or confirm depends on how the values were read, and that is what the policy
learns.

**What the policy sees** (30 numbers): for the amount, the date and the period, whether a value is
held, whether the two readers disagreed, who read it (both, the model only, the rules only, an
earlier turn) and how sure the model was of the words it marked; plus the task, the intent
confidence, whether the person already confirmed, whether they said there is no deadline, whether
the message mentioned a second amount, how many questions were asked, and which were asked.

**What it does not see:** whether a value is correct. It has to infer risk from those signals.

## 2. The rules the network cannot break

`backend/app/ai/dialogue/state.py` is plain code that decides which of the five actions are
**legal** in a state. The network only ranks the legal ones.

* No plan, and no read-back, while the amount is missing or read two ways: the only legal action
  is `ASK_AMOUNT`. The amount is always asked for first.
* A send plan needs its period; a payment plan needs its date settled (a conflict is asked about).
* A read-back only when every value is known, never twice in a row, and never after the turn limit.
* The same file is imported by training and by the API, so they cannot disagree about the rules.

A test checks these rules exhaustively over a grid of states, and another shows that a policy file
that always wants to plan, with the largest possible bias, is overruled by them. The weights are
JSON data, checked against a manifest's SHA-256 and refused on a mismatch or a wrong shape. With
`DIALOGUE_MODE=off`, a missing file or a failed check, the assistant behaves as before (plans as
soon as the amount is known).

## 3. The simulator

The policy was trained against simulated parents, because no data of real parents exists. A parent
has a goal (a payment plan with an amount and, in 85% of cases, a deadline; or a send plan with an
amount and a period) and says it in different ways: with everything in the first sentence, with
only the amount, only the date, or nothing. Parents make typos, sometimes mention an unrelated
amount ("last year I paid GBP 9,000"), sometimes give a date no reader can use ("sometime next
month"), may mistakenly answer "no" to a correct read-back, and lose patience after four questions.

**What is real:** every sentence a simulated parent can say was run through the assistant's own
reading pipeline (the trained reader, the rule reader and the deterministic checks), and the
simulator stores what the assistant perceived: the value, who read it, how sure the model was. So
the noise the policy learns from (a value that was missed, read two ways, or confidently wrong) is
the real system's noise, not an invention. 6,000 goals and about 85,000 perceived sentences
(`ml/rl/bank/`).

**What is assumed:** how parents behave, how often they make typos or mention other amounts, and
the reward.

| Outcome | Reward |
|---------|-------:|
| a correct plan | +1.0 |
| the right deadline (or period) on it | +0.5 |
| a wrong amount | -2.0 |
| a wrong or invented deadline (or period) | -1.0 |
| each question or read-back | -0.05 |
| the parent gives up | -0.5 |

The goals are split 70% train, 10% validation and 20% test by goal, so the test goals are never
used to train or to choose a run.

## 4. Training

Double DQN with action masking: a 30 -> 64 -> 64 -> 5 network scores the actions, the exploration
only tries legal ones, and the Bellman target maximises over the legal actions of the next state
only. Experience replay, a target network, Huber loss, Adam at 5e-4, batch 256, 100,000
episodes (about 200,000 decisions). Three seeds; the run with the best validation return ships.

It trains in about eight minutes on a laptop-class machine with three runs at once. **The GPU does
not speed this up**: the network is tiny and the simulator, which is plain Python, is the
bottleneck. The script uses CUDA if it is there. (The reader in [AI_AGENT.md](AI_AGENT.md) is where
the GPU matters.)

## 5. Results

On 6,000 simulated test conversations (95% intervals in the generated report):

| Policy | Return | Wrong plan | Questions asked |
|---|---:|---:|---:|
| before: plan as soon as the amount is known | +1.164 | 2.8% | 0.44 |
| best hand-written rule (found by search on validation goals) | +1.343 | 0.0% | 1.97 |
| **Raw RL model (before API review)** | **+1.358** | **0.8%** | **1.17** |

* The learned policy is clearly better than the old behaviour (+0.19) and matches or slightly
  beats the best hand-written policy while asking **40% fewer questions**, by accepting a
  small rate of wrong plans. It is a different trade-off, not a free lunch: the hand-written policy
  has 1 wrong plan in 6,000 (0.017%, hidden by one-decimal rounding).
* What it learned, by what it does first: ask for the amount when it is missing (100%), ask for the
  date when only the date is missing (80%), and plan straight away when both readers agree on
  everything (95%). Over whole conversations it reads values back in about a quarter of them.
* It responds to incentives (same seed, retrained with a different reward). With a wrong amount
  costing -10 it reads back 48% of the time instead of 9% and cuts its wrong plans from 1.3% to
  0.4%; with a wrong amount costing -0.5 it reads back 16%; with an impatient parent (-0.3 per
  question) it almost never reads back (1%).
  Under the -10 reward it does **not** quite match the simple "confirm every time" (+1.334 against
  +1.342): DQN finds rare costly events hard to learn from, which is a limit of the method.
* Seeds agree: returns differ by about 0.01 across three seeds.

## 6. What this found about the system

The first evaluation showed a weakness in the existing reading pipeline, not in the policy: when a
parent's real amount cannot be read (a typo) and the message mentions another amount, both readers
can agree on the wrong one with 99% confidence. Confidence cannot flag that, but a count of the
amounts the message mentions can, so it became part of the state. It reduces the problem; it does
not remove it (a message whose only amount is someone else's still looks fine), which is why a
read-back exists at all.

## 7. Limits you should know

* **The parents are simulated and the rewards are my choices.** The policy is only as good as those
  assumptions. The sensitivity table in the evaluation shows how much its behaviour moves.
* **The simulated messages are harder than typical** (20% mention an unrelated amount, 15% have a
  typo in a long word); real parents may be easier or harder.
* **It has never met a real person.** A user study would be the next step.
* **It accepts about 1% wrong plans** in the simulation. The wrong plan is a quote card that the
  person reviews before creating a draft, and a human still approves; set a higher cost for it and
  retrain if that is too much.
* **The state is small** and discrete in nature; a table or a search could do much of what the
  network does. What the learning adds is that the trade-off is found by experience instead of
  designed by hand, and that it adapts when the costs change.
* **No outside review** of the simulator or the policy has been done (R39 and R40 in
  [SECURITY_SELF_ASSESSMENT.md](SECURITY_SELF_ASSESSMENT.md)).

## 8. Reproduce it

```bash
backend/.venv/Scripts/python ml/rl/run_build_bank.py      # the observation bank (needs the reader)
sh ml/rl/run_all.sh                                       # three seeds and three reward variants
ml/.venv/Scripts/python ml/rl/export_policy.py --names dm1 dm2 dm3
ml/.venv/Scripts/python ml/rl/evaluate_rl.py              # writes docs/AI_RL_EVALUATION.md
```

If you retrain, `export_policy.py` writes a new manifest (tests check it matches the bank),
`test_rl_quality.py` refuses a policy that no longer beats the old behaviour, and the evaluation must
be run again (a test fails while the report describes another policy).

## 9. Where the code is

| Path | What |
|------|------|
| `backend/app/ai/dialogue/` | `state.py` (the state, the five actions, the legal-action rules), `policy.py` (NumPy policy, integrity check), `bridge.py` (a reading to a state), `model/` (the shipped weights) |
| `backend/app/ai/orchestrator.py`, `tasks.py` | the policy's turn: ask, read back, or plan; the audit event records the policy, its hash and the action |
| `ml/rl/` | the simulator, the bank builder, the baselines, the trainer, the exporter and the evaluation |
| `backend/tests/test_dialogue_*.py`, `test_rl_*.py` | the tests |
