# The trained explainer: a small language model that rewords the engine's answer

StudyRoute's assistant used to answer from fixed templates, and no live language model had ever spoken
in it. This page describes the model that now does the wording: a small language model, **trained on a
GPU on this project's own data**, that runs on the user's machine with no key and no network, behind
every guard the assistant already had. It says exactly what it does, how it was trained and measured,
including the parts that are modest, and what it cannot do.

The rule that has not changed: **the engine calculates, the AI explains, the human approves, and every
step is logged.** The explainer never calculates, never decides and never adds a number.

## 1. What it does, in one picture

```
question ──► engine (every figure) ──► engine's DRAFT answer ──► explainer rewrites the draft
                                                                       │
                              check_rewrite: no new figure, most figures kept, the disclaimer and any
                              refusal kept, no action claim, no legal claim, "(synthetic)" kept
                                                                       │
                    passes ◄───────────────────────────────────────────┴──────────────► fails
              the number guard and the tool guard run as before                  the engine's draft
                                  │                                              is shown instead
                                  ▼
                              the reply
```

The model is a **draft rewriter**. The orchestrator hands it the question and the engine's draft; it
returns a rewording. Its output is plain text and is thrown away unless every check passes, so the worst
it can do is make an answer a little worse worded, never wrong. The engine's own fact references and
proposed actions are kept; the model cannot add, change or remove them.

**Honest scope.** It rewords what the engine already says. It does not know anything the draft does not
contain, so when the draft does not answer the question (for example "why would my transfer be
declined?" when the engine has no such fact) the rewording still does not. About half of its accepted
answers are identical to the draft (the model learned that copying is often the safest edit). It is a
careful paraphraser, not a second brain.

## 2. How it was trained: verified distillation

A small model fed raw teacher outputs would learn the teacher's habit of inventing a figure. So the
training targets are **checked by code first**:

1. **Pairs.** The real assistant was run on thousands of synthetic scenarios (amounts, currencies,
   countries, charge codes, due dates, payment stages) with questions from the trained reader's data
   (`ml/data/generated`: training questions for training, held-out wording for the test), recording the
   engine's draft for each. 6,000 / 500 / 700 pairs for training, tuning and test. Synthetic only.
2. **Teacher.** An open model, **Qwen2.5-1.5B-Instruct** (Apache-2.0), proposed three rewrites for each
   pair on the GPU, told to answer the question directly and to copy every figure.
3. **Verification.** `check_rewrite` kept only the faithful ones.

| Split | Pairs | Teacher proposals | Passed the checks | Pairs with at least one |
|-------|------:|------------------:|------------------:|------------------------:|
| Train | 6,000 | 18,000 | 7,785 (43.3%) | 3,679 (61.3%) |
| Tuning | 500 | 1,500 | 681 (45.4%) | 320 (64.0%) |
| Test | 700 | 2,100 | 967 (46.1%) | 454 (64.9%) |

**More than half of the raw teacher output was not usable.** On the training set it changed or invented a
figure 2,813 times, lost a refusal 2,302 times ("I cannot approve" turned into something softer), dropped
most figures 2,025 times and lost the "Indicative. Confirm with your AD bank." sentence 1,960 times. That
is why the checks exist and why the student never sees a raw proposal.

4. **Student.** **google/flan-t5-small** (77M parameters, Apache-2.0) was fine-tuned on the verified
   rewrites plus the engine's own draft as a copy example (25% of pairs, and for every pair with no
   verified rewrite): 10,971 training examples, 6 epochs, batch 16, learning rate 3e-4, bf16, on an RTX
   5060 Ti in 12 minutes. Validation loss fell from 0.489 to 0.391. `ml/explainer/train.py`.
5. **Shrinking and export.** The vocabulary was pruned from 32,000 to the 5,124 pieces that occur in the
   data (plus all digit and punctuation pieces); the pruned model wrote the same answer as the full one on
   150 of 150 held-out examples. The encoder and decoder were exported to **ONNX and quantised to int8**:
   21.8 MB and 31.0 MB. Files are data, not code, and their SHA-256 hashes are checked against
   `manifest.json` before they load. The int8 model gives the same wording as the PyTorch one on 90 of
   150 examples (the rest differ in a word or two, which is why the real test is whether the answer passes
   the checks, below). It runs on CPU in `backend/app/ai/explainer/` with a small greedy decoder.

The verified training pairs (a few hundred KB) are in `ml/explainer/release/` so the training can be
reproduced; the teacher's weights and the base model are downloaded, not committed.

## 3. Results on questions it never saw (700 held-out pairs)

Every output was judged by the same check the live assistant uses.
Numbers from `submission/evidence/ai_explainer_evaluation.json`.

| | Trained explainer | The same model, untrained | Teacher (raw, before the checks) |
|---|---:|---:|---:|
| Answers that pass every check and would be shown | **80.9%** | 20.1% | 46.1% of proposals |
| Answers where the model changed nothing (copied the draft) | 48.6% | 0.4% | – |
| Answers that invented a figure | **0.4%** (3 of 700) | 1.4% | 15.3% of proposals |
| Mean length in words (the draft is 64.9) | 58.8 | 14.7 | – |

**Figures in the answers, against the engine's draft** (micro-averaged):

| | Figure precision (no invented figure) | Figure recall (figures kept) |
|---|---:|---:|
| Raw model output, before any check | **99.8%** | **97.5%** |
| What the person actually reads (the model's answer if it passed, else the engine's draft) | **100%** | **98.8%** |
| Untrained model, raw | 96.1% | 21.3% |

Why the other 19.1% are not shown: 15.6% ran out of room (`UNFINISHED`), 2.6% lost the disclaimer, 0.6%
dropped most figures, 0.4% invented one. They fall back to the engine's draft, which is correct.

**By kind of answer** (share shown): 100% for charges, checklist, costs, draft, help, KYC, limits,
approval requests and status; 98% for deadlines; 80% for comparisons; **40% for send-plan cadence, 32%
for payment plans, 21% for arrival guides and 0% for stress tests**. The long structured answers are
longer than the model's 200-token room, so it cannot finish them. A measured length limit
(`MAX_DRAFT_WORDS = 120` in `client.py`) now skips the model for those, which costs nothing (up to 120
words every answer was accepted in the check, 14 of 14 per length band; from 120 to 160 words it never
produced an accepted answer) and avoids a wait of 7 to 9 seconds.

**Speed** (CPU, about 0.8 s for a typical answer, median 1.2 s over the evaluation): fast enough for a
chat. Memory: about 200 MB.

**Accuracy, precision, recall.** For this model the meaningful versions are the two above: *figure
precision* (of the figures an answer states, how many are the engine's: 99.8% raw, 100% shown) and
*figure recall* (of the engine's figures, how many are kept: 97.5% raw, 98.8% shown), both above 90%.
They are not a measure of how good the wording is. "Accepted by the checks" (80.9%) is the share of the
model's own answers that are good enough to show; the rest is the engine's own answer.

## 4. Where it can still go wrong, and what limits the harm

* **It can reword badly.** Its wording is sometimes clumsy or says nothing new (see the samples in
  `ml/explainer/data/samples.json`). The checks catch wrong numbers, lost refusals and lost disclaimers;
  they cannot judge style. Limit: the engine's answer is always one failed check away.
* **It cannot judge a claim the checks do not know.** The checks look for figures, the disclaimer,
  refusal words, action and legal claims, promises and the "(synthetic)" label. A subtle new claim in
  ordinary words could pass them. The assistant's own claim guards and the number guard run afterwards.
  Limit: the model has no tools and no permissions; it cannot act on a claim.
* **Trained on synthetic questions** and judged on synthetic ones. It has not been tested on real parents.
* **It is not a chat model.** It only rewords a draft the engine has already made.
* **A bigger external model still takes precedence.** A configured key (Anthropic, an OpenAI-compatible
  host, Gemini or Groq) or the Hugging Face Space replaces it; the same checks apply to those.

Controls: `EXPLAINER_MODE=off` returns to the engine's own wording; a changed file fails its SHA-256
check and is not loaded; nothing opens a network connection (a test asserts it); the chip in the
assistant says "Trained explainer" and its title says what it does.

## 5. Reproduce

```bash
cd backend && .venv/Scripts/python ../ml/explainer/generate_pairs.py       # the engine's drafts
cd .. && ml/.venv/Scripts/python ml/explainer/teach.py --split train       # the teacher (GPU), then val and test
cd backend && .venv/Scripts/python ../ml/explainer/verify_candidates.py --split train   # the checks
cd .. && ml/.venv/Scripts/python ml/explainer/train.py --epochs 6 --batch 16             # the student (GPU)
ml/.venv/Scripts/python ml/explainer/export.py --run explainer-v1                        # prune, ONNX, int8
ml/.venv/Scripts/python ml/explainer/baseline_zero_shot.py --split test --limit 700
cd backend && .venv/Scripts/python ../ml/explainer/evaluate.py                           # the table above
pytest tests/test_explainer_verify.py tests/test_explainer_integration.py tests/test_explainer_model.py
```

## 6. Tests

`test_explainer_verify.py` (13: what each check refuses), `test_explainer_integration.py` (13: the client
and the orchestrator with a stand-in model: a faithful rewrite is shown, an unfaithful one is replaced
by the engine's draft, proposals survive, the model cannot make the assistant approve anything, a draft
too long for it is not run) and `test_explainer_model.py` (7: the real files, accepted share, no invented
figure, refusals kept, no network, speed, and the recorded evaluation against its floors).
