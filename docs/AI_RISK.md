# The risk model: what it learned, what it decides, and what it cannot

A small network, trained on a public data set of **synthetic** bank transactions, that reads each
payment and rates how unusual it looks: low, medium or higher, with the factors that drove the rating
(`docs/BANK_REVIEW.md`). **Every payment gets a risk score from 0 to 100, built from four factors (amount,
frequency, timeline, person). A low score shows no warning; a medium or high score shows a warning and
decides which payments a person at the bank looks at, and in what order.** Whatever the score, every
payment needs a person's authorization.
It never clears, declines or approves anything, it never accuses anyone, and a human with a fresh MFA
proof gives the answer. This page says exactly how it was built, how it was measured, including the
results that do not look good, and where it must not be trusted.

> **Read this first.** On the data it was trained for, it ranks well: on a later period it never saw it
> puts 63% of the flagged transactions in the top 1% of its ordering (random order finds 1.2%). But it
> **cannot** reach 90% precision and 90% recall together on this data, no model of this size can, and
> some of what it learned is a habit of the data generator rather than something true about money. The
> sections below show the numbers behind both statements.

> **Which model?** Ten kinds of model were tried on the same data and split: see [AI_RISK_MODELS.md](AI_RISK_MODELS.md) for every result.
> The model described below is the one shipped so far, a small neural network on eight inputs.

## 1. The data

| | |
|---|---|
| Data set | IBM *Transactions for Anti Money Laundering (AML)*, **HI-Small**: 5,078,345 synthetic transactions over about 18 days, 518,573 accounts, **5,177 labelled as laundering** by the generator (0.10%) |
| Made by | IBM Research's generator; Altman, Blanuša, von Niederhäusern, Egressy, Luksic and Bitar, "Realistic Synthetic Financial Transactions for Anti-Money Laundering Models", NeurIPS 2023 (Datasets and Benchmarks) |
| Licence | **CDLA-Sharing-1.0**. The data is not in this repository (`ml/aml/data/` is ignored); `ml/aml/fetch.py` records its size and SHA-256 and `ml/aml/SOURCE.json` says where it came from |
| Why this one | It is the largest openly licensed set with per-transaction laundering labels. The other candidate (SAML-D) is licensed non-commercial and share-alike, which we did not want to build on |

Nothing in it is a real person or account. Everything the model learned was "laundering" *as the
generator draws it*.

## 2. How it was trained

* **Split by time, not at random.** The first 60% of the timeline trains (3,047,216 transactions, 2,299
  flagged), the next 20% tunes (1,015,565; 1,081) and the last 20% is the test (1,015,564; 1,797). A
  bank scores tomorrow's payments with what it learned yesterday, so the test is later than everything
  the model saw. Every count of "earlier payments" uses only earlier rows.
* **Eight inputs**, all things the sandbox knows about a payment, which the product calls its four
  factors: the **amount** (its size compared with other payments in the same currency, a percentile);
  the **frequency** (how many payments this household made in the last day, the last week and ever);
  the **timeline** (how long since the last one); and the **person** (whether this household has paid this
  receiver before, and whether it has any history at all). The training table is built by `ml/aml/build.py` with the same function
  (`app.ai.risk.features.vectorise`) the app uses.
* **Bands with a meaning.** The model's score is turned into three bands with cut-offs set on the tuning
  period only: `HIGH` is the top 0.1% of its payments and `MEDIUM` the next 0.4%. Each band carries the
  share of its payments that the data flags, measured on the tuning period (`HIGH` 41.6%, `MEDIUM` 3.2%,
  `LOW` 0.05%), so that "high" says something a person can check. `MEDIUM` and `HIGH` open a review.
* **Reasons.** For each payment the model hides each group of inputs in turn (the amount; payments close
  together; little history; a new receiver) and reports the groups whose removal lowers the score the
  most. They are shown in plain words and are the model's own contribution, not a rule.
* **Two models, one chosen on the tuning period.** A plain logistic model and a two-layer network
  (8 → 128 → 64 → 1, about 9,500 weights). Trained on your GPU (RTX 5060 Ti) in seconds. The network won on
  the tuning period and is the one shipped (`backend/app/ai/risk/model/risk.json`, 233 KB, checked by a
  SHA-256 manifest at start-up, run in NumPy).
* **What was chosen on which period.** The network against the logistic model, and the threshold for the
  best-F1 point, were chosen on the tuning period only. Which inputs to drop was decided on a principle
  (section 3: the label counts per channel come from the whole data set), then confirmed with an
  ablation that prints test-period numbers; those numbers describe the model, they were not used to pick
  the final model or any threshold.

## 3. What was left out on purpose (and how we found out)

The first version also saw the payment channel (wire, ACH, cheque, cash, card, bitcoin), whether the
currencies differed, whether the two banks were the same, the hour of the day and how many payments the
receiver got from anyone. It scored higher. Then `ml/aml/ablate.py` counted the labels per channel:

| Channel | Transactions | Labelled laundering |
|---------|-------------:|--------------------:|
| ACH | 600,797 | **4,483** (0.75%) |
| Cash | 490,891 | 108 |
| Bitcoin | 146,091 | 56 |
| Cheque, credit card | 3,187,655 | 530 |
| Reinvestment | 481,056 | 0 |
| **Wire** | 171,855 | **0** |
| **Any cross-currency transfer** | 72,170 | **0** |

In this data **no wire and no cross-currency transfer is ever labelled as laundering**. A model that saw
those inputs would learn that a cross-currency wire, which is exactly what every StudyRoute payment is,
is the safest thing in the world. That is the generator's habit, not a fact about money, and it would
have pushed every real payment to the bottom of the queue. The ablation also showed that dropping the
channel inputs cost nothing (average precision 0.449 without them, 0.412 with, in the first pass;
`submission/evidence/ai_risk_ablation_first_pass.json`). So the channel, the currencies, the bank and the
time of day are not inputs. The receiver's fan-in was removed for a different reason: a university
legitimately receives many payments, and a model that punished that would punish every family.

## 4. Results on the test period

Random order and "biggest amounts first" are the baselines. Numbers from
`submission/evidence/ai_risk_training.json` and `ai_risk_operating_points.json`.

| Ordering | Average precision | Area under the ROC curve | Flagged found in the top 1% | in the top 5% |
|----------|------------------:|-------------------------:|----------------------------:|--------------:|
| Random | 0.0018 | 0.508 | 1.2% | 5.4% |
| Biggest amounts first | 0.0037 | 0.755 | 2.1% | 3.1% |
| Logistic model | 0.088 | 0.770 | 38.6% | 55.8% |
| **Two-layer network (shipped)** | **0.437** | **0.963** | **63.2%** | **80.7%** |

Only 0.18% of the test transactions are flagged, so average precision of 0.43 is about 240 times random.

**First payments to a receiver only.** This is the group StudyRoute payments belong to (a family's first
tuition payment to a university). In it 3.5% of the test rows are flagged (1,417 of 40,349), which is a
property of the generator. There the network gets average precision 0.545, ROC 0.882 and finds 24% of
the flagged ones in its top 1% (about 17 times better than random there, which finds 1.4%, but far less than the 63% above).

## 5. Accuracy, precision and recall, with no flattering

Precision and recall trade against each other: send more payments to a person and you catch more and
waste more of their time. The point "best F1" was picked on the tuning period; everything is measured on
the test period.

| Operating point (all payments) | Sent to a person | Accuracy | Precision | Recall |
|--------------------------------|-----------------:|---------:|----------:|-------:|
| Never flag anything | 0 | 99.82% | – | 0% |
| **Best F1** (threshold from the tuning period) | 962 | **99.86%** | **67.5%** | **36.1%** |
| Top 0.5% of the ordering | 5,077 | 99.53% | 20.7% | 58.5% |
| Top 2% | 20,311 | 98.08% | 6.4% | 72.4% |
| Top 5% | 50,778 | 95.11% | 2.9% | 80.7% |
| Top 10% | 101,556 | 90.13% | 1.5% | 85.7% |

* **Accuracy is above 90% at every point, and that means nothing.** Answering "not flagged" every time
  is 99.82% accurate and catches no one. The metric hides the whole problem when only 0.1% are flagged.
* **Precision and recall cannot both exceed 90% here.** At the best-F1 point they are 67.5% and 36.1%.
  To catch 85% of the flagged transactions precision falls to 1.5%; to get 90% precision recall falls to
  about 13% (first payments, top 0.5%: precision 92.0%, recall 13.1%). The curve does not pass through
  (90%, 90%), and no setting of a threshold can make it.
* For first payments to a receiver the best-F1 point is precision 73.0%, recall 40.2%, accuracy 97.4%.

We did not try to reach 90/90 by evaluating on an easy subset, by choosing the threshold on the test
period, by letting the future into the inputs or by counting only what the model got right. Any of those
would give a bigger number and a false claim.

### The routing the review desk actually uses

The desk sends a payment to a person when the model rates it `MEDIUM` or `HIGH`. Cut-offs fixed on the
tuning period, measured on the test period (`ai_risk_operating_points.json`):

| Routing | Sent to a person | Accuracy | Precision | Recall |
|---------|-----------------:|---------:|----------:|-------:|
| Medium or high | 3,474 of 1,015,564 (0.34%) | 99.68% | 29.2% | 56.5% |
| High only | 1,548 (0.15%) | 99.83% | 52.7% | 45.4% |
| Medium or high, first payments to a receiver only | 3,416 of 40,349 (8.5%) | 93.0% | 29.2% | 70.4% |

`MEDIUM` alone is weak (10.4% precision, 11.1% recall), which is why its hit rate is shown to the person.
Treat it as "worth a look". Precision and recall are both below 90% at every setting, as section 5 says.

## 6. Where it can mislead (and what limits the harm)

* **It learned the generator.** Almost all its signal is "a payment to a receiver this household has
  never paid" plus the household's recent activity (`ablate.py`: without the receiver pair, average
  precision falls from 0.39 to 0.008). That is how the generator draws laundering. A family's first
  tuition payment is also a payment to a new receiver, so the model will often rate honest payments
  as "unusual". This is why it is only a hint.
* **It can be oddly wrong.** In a spot check a routine instalment to a known university scored 0 and a
  new receiver straight after five quick payments scored 99, which is sensible. An earlier version also
  scored any round amount as the safest payment possible (a swing of 180 in the model's own units), because
  almost no payment in the data is round and the network learned an extreme rule from a handful of
  examples. Anyone could have used that, so the round-amount inputs were removed and the model retrained
  (section 3). Other quirks of the same kind may remain, which is why a person decides.
* **It has never seen a real cross-border wire label**, because the data holds none (section 3).
* **So it only routes.** A payment it rates low takes the fast lane (even a large one: the parent still
  approves with MFA and the sandbox caps still apply); a medium or high payment waits for a person, who
  decides. The queue is ordered by lateness first and then by the model's rating
  (`backend/tests/test_risk_scorer.py` checks this). It cannot clear, decline or approve anything. The
  model's name, band and routing are written to the audit log with each use. `RISK_MODE=off` removes it,
  and then the plain rules decide again and the page says "No AI reading". A name-list match (like the
  sanctions mock) still goes to a person whatever the model says.
* **Not validated on real payments**, on real people or on this corridor. No claim is made that it finds
  real laundering.

## 7. Reproduce

```bash
ml/.venv/Scripts/python ml/aml/fetch.py            # check the download, record its SHA-256
ml/.venv/Scripts/python ml/aml/build.py            # about 40 seconds: the training table
ml/.venv/Scripts/python ml/aml/train.py            # on the GPU, seconds; writes the model and the manifest
ml/.venv/Scripts/python ml/aml/ablate.py           # what the model relies on
ml/.venv/Scripts/python ml/aml/operating_points.py # accuracy, precision, recall at each threshold
cd backend && pytest tests/test_risk_signals.py tests/test_risk_history.py tests/test_risk_scorer.py
```

The tests check that the two ways of counting earlier payments agree, that the files are verified before
use, that a wrong model is refused, and that the queue is ordered by the rules first.
