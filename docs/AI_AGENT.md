# The trained agent: a small model that reads what a parent types

StudyRoute's assistant used to understand a message with fixed patterns (regular expressions). It
now also has a **small language model, fine-tuned on a GPU for this job**. This page says what the
model does, what it is not allowed to do, how it was trained, what data it learned from, how well
it works (with the numbers, including the bad ones) and how to reproduce all of it.

The rule that has not changed: **the engine calculates, the AI explains, the human approves, and
every step is logged.** The model is a *reader*. It decides what the person wants and marks which
words carry an amount, a currency or a date. It never calculates, never approves, and never writes a
number that the person did not type.

## 1. What the model does

One model, two jobs, on every message:

| Job | Output | Example: "kindly help me send ten thousand pounds for my son's tuition, last date end of November" |
|-----|--------|-----------------------------------------------------------------------------------------------------|
| **Intent** (one of 14) | what the person wants | `PLAN`: quote it, rank providers, plan the deadline |
| **Slots** (7 kinds) | the exact words that carry a value | `ten thousand` = amount, `pounds` = currency, `end of November` = date |

The 14 intents are `PLAN`, `CADENCE`, `COMPARE`, `CHARGES`, `DEADLINE`, `CHECKLIST`, `LIMITS`, `KYC`,
`STATUS`, `DRAFT`, `REQUEST_APPROVAL`, `HELP`, `OUT_OF_SCOPE` and `ATTACK`. The slots are `AMOUNT`,
`CURRENCY`, `DATE`, `DURATION`, `CHARGE`, `PURPOSE` and `PROVIDER`.

The rule-based reader could not read that message. The model can, and plain code then turns the marked
words into GBP 10,000.00 due 30 November 2026. The engine does the rest.

It also holds a conversation. If the assistant asks "I still need an amount and a currency" and the
person answers "GBP 10,000 by 28 October", the assistant finishes the task it asked about instead of
starting over (the page sends back what was already understood; the server validates it like any
other input).

## 2. How a message flows

```
message
  │
  ├─► policy filter (regular expressions: instruction override, action requests, secrets) ──► blocked?
  │
  ├─► rule reader ─────────────┐
  │                            ├─► check and combine ──► intent + typed values
  └─► trained reader ──────────┘        ▲
        marks words only                │  deterministic: normalize.py, slots.py
                                        │  (numbers, currencies, dates, durations)
                                        ▼
        task runner ──► deterministic engine (every number) ──► facts
                                        │
                     template (or optional LLM) ──► number guard ──► reply ──► audit log
```

What "check and combine" means:

* **Values come from code, not from the model.** The model marks `10,000`; `normalize.py` turns it
  into 1,000,000 minor units (integers, never floats). A span that cannot be read exactly (`1,5`,
  `soon`, `31 February`) gives *nothing*, and the assistant asks. Amounts with no exact reading are
  never guessed.
* **Two readers must agree.** If the rule reader and the model read the same field differently, the
  field is left empty and the assistant says what it read twice and asks once.
* **The model's intent is used only when it is sure enough.** The thresholds were chosen on a
  separate data split. Starting something (a quote, a draft, an approval request) needs more
  confidence than answering a question, and a question about limits or legality can never start a
  quote, even if the model says so.
* **`ATTACK` can only add a block.** A confident "this is an instruction override or an action
  request" blocks the message exactly like the policy filter does, with a fixed refusal. The model
  can never lift a block the filter raised.
* **Nothing here can act.** The reader has no permission of its own. The AI account still cannot
  approve, submit, cancel, allowlist or change a limit; only a human parent with a fresh MFA proof can.

Safety properties of the artefact itself:

* The model is an **ONNX graph** (data, not code), so loading it cannot run code the way a pickled
  model can. Its SHA-256, and the vocabulary's, are checked against `manifest.json` at start-up. A
  mismatch means the reader is not used and the assistant falls back to its rules.
* It runs **locally on CPU** (median 18 ms, 95th percentile 57 ms a message). Nothing leaves the machine. With no
  `onnxruntime`, no model file, or `NLU_MODE=off`, the assistant runs on the rules alone, so template
  mode with no key still works exactly as before.
* Every AI audit event records which reader understood the message, the model's short hash and its
  confidence (`reader=studyroute-nlu-v1@94146e8c4b72 intent=PLAN:0.99`). The message text itself is
  not stored; only its hash is, as before.
* The chat shows **"How I read this"**: the intent, how sure the model was, and each marked word
  with what it was taken for. A person can see why the assistant did what it did.

## 3. The model

| | |
|---|---|
| Base model | `BAAI/bge-small-en-v1.5` (MIT licence), 33.4 million parameters, 12 layers, 384 wide |
| Fine-tuned for | joint intent classification (first token) and word tagging (BIO), one loss each |
| Shipped as | int8-quantised ONNX, 33.8 MB (`backend/app/ai/nlu/model/`); accuracy on validation did not drop by more than 0.3 points, which was the condition for keeping the quantised file |
| Tokenizer | the project's own WordPiece (`tokenizer.py`), used in training and in the API, so the two cannot disagree; every word keeps its character offsets |
| Training | one NVIDIA GeForce RTX 5060 Ti (16 GB), PyTorch 2.11 with CUDA 12.8, bf16, AdamW at 8e-5, batch 64, 6 epochs, seed 7. A few minutes end to end |
| Calibration | temperature 1.4 so a confidence of 0.9 means about 90%; thresholds (intent 0.80, action 0.50, attack 0.50) chosen on the dev split by running the agent's own logic |
| Cost at run time | median 18 ms and 95th percentile 57 ms per message on CPU (`submission/evidence/ai_evaluation.json`) |

**Choosing the base model.** Six candidates were fine-tuned with the same data and settings and
compared on the *dev* split, which holds message templates the model never trained on. No test set
was used to choose. The table is in `submission/evidence/ai_backbone_ablation.json` (generated by
`ml/collect_ablation.py`); the contrastively pre-trained sentence encoders generalised much better to
unseen wording than a plain MiniLM, which is why `bge-small-en-v1.5` was chosen.

| Base model | Learning rate | Dev intent accuracy | Dev span F1 |
|---|---|---|---|
| bge-small-en-v1.5 (chosen) | 8e-05 | 95.2% | 98.5% |
| e5-small-v2 | 8e-05 | 93.5% | 97.1% |
| bge-small-en-v1.5 (lr 5e-5) | 5e-05 | 93.3% | 98.8% |
| all-MiniLM-L12-v2 | 8e-05 | 92.5% | 97.0% |
| MiniLM-L12-H384 | 8e-05 | 89.2% | 98.6% |
| gte-small (did not train: the loss never fell; not investigated) | 3e-05 | 24.1% | 0.0% |

Six runs, one seed each, so a difference of about a point is within the run-to-run noise; the gap to the plain MiniLM is not.

## 4. The data

**There is no public data set of parents paying tuition abroad**, so the training data is built, and
every limit of that is stated here.

| Source | What | How it is used |
|--------|------|----------------|
| **Generated messages** (original work, `ml/data/`) | Sentences composed from 565 templates across the 14 intents, with a random amount in 6 currencies and many written styles (`GBP 10,000`, `£10k`, `ten thousand pounds`, `10000 quid`, `1,00,000`), many date styles (`28th Oct`, `end of November`, `in three weeks`, `next Friday`), then typos, politeness, casing, code-switching ("Assalamu alaikum", a little Banglish) and numbers that are *not* values (invoice numbers) | training, validation, dev and held-out tests |
| **Banking77** (PolyAI, **CC BY 4.0**) | 13,083 real customer questions to a bank, 77 categories | 46 card, ATM and account-admin categories become `OUT_OF_SCOPE` (the assistant does not handle them). 17 categories that are about fees, timing, status and identity checks are mapped to StudyRoute's own intents, so the model sees real human wording for those intents and cannot learn "natural sentence means out of scope" |
| **Hand-written hard set** (136) and **blind set** (113) | Messages written by hand with annotations | test only |

Every labelled span is also run through the deterministic normalizer; an example whose span cannot be
read as a value is dropped, so the labels are never ahead of what the code can understand.

**Splits, and why they are not the same thing:**

| Split | Examples | Purpose |
|-------|---------:|---------|
| train | 35,588 | learning |
| val | 2,279 | choosing the best epoch |
| dev | 10,977 | templates never trained on; picks the base model, the temperature and the thresholds |
| test | 1,708 | new values in the training templates: a sanity check, deliberately easy |
| test_heldout | 11,004 | a different set of unseen templates: never tuned on |
| natural | 680 | real Banking77 test questions mapped to StudyRoute intents |
| oos_public | 698 | real Banking77 test questions that are out of scope |
| hard | 136 | hand-written; **used for error analysis during development**, so it is a diagnostic, not a clean test |
| blind | 113 | hand-written **after the model, data and thresholds were frozen**; now re-evaluated (not a new blind study) |

A test checks that no test message is in the training data and that the shipped model records the
hash of the exact data it was trained on (`backend/tests/test_ml_dataset.py`). One leak was found
and fixed that way: Banking77's own test split repeats a few of its training messages.

**Ethics and privacy.** No real person's message is used. The generated names, universities, amounts
and account numbers are invented. A test scans the data for e-mail addresses.

## 5. Results

The complete, generated report is [AI_EVALUATION.md](AI_EVALUATION.md); every number in it comes from
`ml/evaluate.py` running the shipped model. Three systems are compared on the same messages:
**rules** (the old regular-expression reader plus the policy filter), **reader** (the model alone) and
**agent** (what the product runs: the model, the deterministic checks, the thresholds and the filter).

On the **blind set** (113 messages, now re-evaluated (not a new blind study); at this size a result is good to about plus or
minus 7 points):

| | Rules | Agent |
|---|---:|---:|
| Intent routed correctly | 61.1% | **88.5%** |
| A plan request read completely and exactly (intent, amount, currency, date) | 57.6% | **100%** (33 requests) |
| Attacks blocked | 28.6% | **92.9%** (14 attacks) |
| Harmless messages blocked | 2.0% | 2.0% |
| Messages that are not a request for a quote, draft or approval but were routed to one | 1.4% | **0.0%** |

On **real customer questions** (Banking77 test, mapped to StudyRoute intents, 680 messages) the rule
reader is right 40.1% of the time and the agent 95.1%. On unseen templates (11,004 messages) 62.0%
against 90.2%.

**What the numbers do not say.** The generated data teaches the model the patterns of its own
generator, so the easy test is near perfect and means little. The held-out and natural sets carry the
weight. The blind set is small. Where the agent is weak, the report shows it: on unseen templates it
blocks 85% of attacks, not 100%, and it routes 4.7% of non-request messages to a task (for example a
question about limits that sounds like a plan). That last error is bounded by design: a task is at
most a quote card the person can ignore, never a payment.

## 6. Limits you should know

* **The data is synthetic and English.** There is a little Banglish and almost no other language.
  Nobody has tested this on real parents.
* **Attack detection is one extra layer, not the defence.** The real controls are the permission
  tiers, the MFA proof bound to the action, and the policy filter. The model catches paraphrases the
  filter misses; it will miss some novel ones (about 7 in 100 in the blind set).
* **Banking77 is about a UK neobank**, so its wording is not the wording of a Bangladeshi AD-bank
  customer.
* **Confidence thresholds were tuned on generated dev data.** On a different population they may sit
  in the wrong place.
* **Relative dates ("next Friday") count from the sandbox clock.** Two readers must agree on a value
  before it is used, and anything ambiguous ("next month", "soon") is asked about, not guessed.
* **The model has not been red-teamed by outsiders.** See
  [SECURITY_SELF_ASSESSMENT.md](SECURITY_SELF_ASSESSMENT.md), risks R32 to R35.

## 7. Reproduce it

You need Python 3.12 and, to train, an NVIDIA GPU. Running the assistant needs none of this: the
trained model is committed.

```bash
# 1. a training environment (the CUDA build for current NVIDIA cards, including RTX 50 series)
python -m venv ml/.venv
ml/.venv/Scripts/python -m pip install torch==2.11.0 --index-url https://download.pytorch.org/whl/cu128
ml/.venv/Scripts/python -m pip install -r ml/requirements.txt

# 2. build the data (downloads Banking77 once)
backend/.venv/Scripts/python ml/data/build_dataset.py

# 3. train, export to ONNX, calibrate
ml/.venv/Scripts/python ml/train.py --backbone BAAI/bge-small-en-v1.5 --name bge --epochs 6 --lr 8e-5
ml/.venv/Scripts/python ml/export.py --name bge

# 4. measure it and write docs/AI_EVALUATION.md
backend/.venv/Scripts/python ml/evaluate.py
```

Training takes a few minutes on the GPU it was built with. If you retrain, `ml/export.py` writes a
new manifest, `test_ml_dataset.py` checks that it matches the data, `test_nlu_quality.py` refuses a
model that falls below the floor, and `ml/evaluate.py` must be run again (a test fails while the
report describes a different model).

## 8. Where the code is

| Path | What |
|------|------|
| `backend/app/ai/nlu/` | `schema.py` labels, `tokenizer.py`, `normalize.py` (words to typed values), `slots.py`, `runtime.py` (ONNX, integrity check), `understanding.py` (check and combine), `model/` (the shipped files) |
| `backend/app/ai/orchestrator.py` | calls the reader, applies the model's block, records it in the audit log |
| `ml/` | `data/` (generator, templates, hard and blind sets, generated splits), `train.py`, `export.py`, `evaluate.py`, `collect_ablation.py` |
| `backend/tests/test_nlu_*.py`, `test_ai_reader_agent.py`, `test_ml_dataset.py` | the tests above |
