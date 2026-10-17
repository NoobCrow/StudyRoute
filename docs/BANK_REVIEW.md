# The sandbox bank's review desk

Most payments a family makes need nobody at the bank to stop and look. A few do. This page describes how
StudyRoute handles that, **in the sandbox**: an AI model reads every payment and says how unusual it
looks, the payments it rates higher go to a person at the bank, who says yes, no or "tell me more" from
one page, and a parent who has never dealt with an AD bank is told in plain words what is happening and
what to prepare.

**In short:** every payment gets an AI risk score from four factors (amount, frequency, timeline,
person). A low score shows **no warning**; a medium or high score shows a **warning** and sends the
payment to a person at the bank. The score never replaces authorization: **every payment needs a
person's authorization whatever its score** (the parent's own fresh MFA code, always), and one setting
(`review.bank_authorizes_every_payment`) makes the bank's yes necessary for every payment too.

> **What this is not.** It is not anti-money-laundering screening, and nothing here tells anyone that a
> payment is legal or illegal, genuine or criminal. The bank is simulated, the reviewer is a demo account,
> and the AI model learned from **public synthetic practice data**, not from real people or real
> payments. It shows the *shape* of a better hand-off between a family and a regulated bank; a real bank
> would bring its own screening, thresholds and people. Every screen and answer says
> "Indicative. Confirm with your AD bank."

## 1. The idea in one picture

```
parent requests approval
        │
        ▼
 the AI model reads the payment ──► a risk band (low / medium / higher), what drove it, how that band
        │                            fared in the practice data
        ├── low (no warning) ───►  FAST LANE: nobody waits, the parent authorizes with MFA as before
        │
        │ medium or higher (or a name-list match)
        ▼
 REVIEW OPENS ──► the reviewer's queue (most overdue first, then the AI's reading)
        │                  │
        │                  ▼
        │        one-page brief: facts, the AI's reading and reasons, what to ask
        │                  │
        │      Clear (yes) │ Ask for more │ Decline (no)   ← a human, with a fresh MFA code
        ▼                  ▼               ▼                  for this payment
 the parent cannot   parent answers    payment rejected,
 approve until       in a few words    the reason shown
 the bank clears it  (clock restarts)  in plain words
```

## 2. Who decides that a person must look: the AI model

`backend/app/ai/risk/` holds a small neural network, trained on your GPU on the public IBM synthetic
transaction data (`docs/AI_RISK.md` has the data, the method, every result and every limit). For each
payment it reads eight numbers the sandbox knows, which make up its four factors: the **amount** (how
large the payment is next to others in its currency), the **frequency** (how many payments this
household made in the last day, week and ever), the **timeline** (how long since the last one) and the
**person** (whether this household has paid this receiver before) and gives:

* a **band**: `LOW`, `MEDIUM` or `HIGH`, from cut-offs set on a tuning period (`HIGH` is the top 0.1% of
  the practice data's payments, `MEDIUM` the next 0.4%);
* a **risk score from 0 to 100** on every payment (how much more unusual than the practice payments it
  looks);
* a **warning** only when the band is medium or high: a low score shows "No warning";
* a **hit rate** for the band, measured on the tuning period (for `HIGH`, 41.6% of such payments were
  flagged in the data; for `MEDIUM`, 3.2%; for `LOW`, 0.05%) so that "high" has a meaning;
* the **four factors**, each shown as raising, lowering or not affecting the score (found by hiding each
  factor in turn and seeing how much the score drops), with a plain sentence: *Amount*, *Frequency*,
  *Timeline* and *Person*.

`MEDIUM` and `HIGH` show the warning and open a review. `LOW` shows no warning and takes the fast lane
(unless `review.bank_authorizes_every_payment` is on, when every payment waits for the bank's yes). The model is the router; it is **not** the
decider: it cannot clear, decline or approve, and the reviewer and the parent still sign with MFA.

What stays as plain rules, and why:

| Rule | Role now | Why it is a rule |
|------|----------|------------------|
| `BANK_AUTHORIZES_ALL`: the setting above, off by default | sends every payment to a person, whatever its score | It is the bank's own policy, not a risk estimate |
| `NAME_CHECK`: the receiver's name contains the sandbox test token | still sends the payment to a person | A name-list match is a lookup, like the sanctions mock, not a risk estimate |
| `LARGE_AMOUNT`, `POSSIBLE_SPLIT` (thresholds in `config/rules.yaml: review.*`, `verified: false`) | shown as **context** to the reviewer ("USD 41,967 against the sandbox line of USD 40,000") | They no longer decide; the AI's reading does |
| `NEW_RECIPIENT`, `NO_INVOICE` | context for the reviewer and the parent | Facts to check, not risk |
| **All of the above, as the decider** | **only when the model is not loaded** (`RISK_MODE=off`, files missing or a failed hash check) | So the desk never runs without any check; the page then says "No AI reading" |

## 3. What the reviewer sees and does

The queue (**Bank review** in the sidebar, reviewer accounts only) is ordered by urgency first (past the
target time, then due soon, then on time) and, within that, by the AI's reading (higher first). Opening a
payment shows one page:

* who pays whom, how much, for what, through which provider, the due date, the documents on file;
* **the AI's reading**: the band, how unusual, what that band meant in the data, what drove it;
* any context from the plain rules, and the one thing worth checking for each;
* a **rule-based hint** (for example "ask for the fee demand note first"), labelled as a hint;
* the parent's answer, if the bank asked something earlier;
* three choices: **Yes, clear it** · **Ask for more** · **No, decline it**, with nothing pre-selected.

Asking or declining needs a listed reason (`review.decline_reason_codes`) and a note the parent can read.
**Every answer is signed with a fresh MFA code bound to that payment** (`review_payment`, single use, five
minutes). A proof made for approving the payment cannot be used here.

## 4. The clock and the reminder

When a review opens, a target time starts (`review.decision_target_hours`, 24 in the sandbox; a real bank
sets its own). The parent sees "about 19 h left of the bank's 24-hour target", and later "about 3 h past
the target". The queue sorts the most overdue first. After the target time the parent may send a reminder
(not more than one every four hours); a reminded, overdue review is marked in the queue. If the bank asks
a question the clock pauses until the parent answers, and then starts again.

This does not *force* a bank to decide, and no software can. It makes a slow decision visible to both
sides and removes the usual reasons for it: the reviewer gets one page with everything needed, and the
parent knows what to prepare. The queue reports the average time to decide.

## 5. Who can do what

| Action | Parent | Student | Reviewer (admin) | AI assistant |
|--------|:------:|:-------:|:----------------:|:------------:|
| Read the plain-language page (`review:read`) | yes | yes | yes (the brief) | yes |
| Answer the bank's question, send a reminder (`review:answer`) | yes | no | no | **no** |
| Clear, ask or decline (`review:decide`) | no | no | **yes, with MFA** | **no** |

Each rule is covered by a test (`backend/tests/test_bank_review.py`, `test_risk_scorer.py`):

* A flagged payment **cannot be approved** until a reviewer clears it (`BANK_REVIEW_PENDING`, shown as a
  blocker and disabling the Approve button).
* Declining uses the same rejection as before and writes its own audit event.
* Every step (opened, fast lane, decided, answered, reminded) writes an audit event in the same
  transaction, with the model's name and the routing (`routing=ai risk=MEDIUM:97`).
* "Reset my data" removes the reviews; the parent's answer is sealed with the project's field cipher.
* The reviewer's yes does not replace the parent's: after a yes, the parent still approves with their own
  fresh MFA code.

## 6. Where the AI is, and where it is not

| Part | What it does | What it cannot do |
|------|--------------|-------------------|
| **The risk model** | Reads every payment, rates it low / medium / higher, says what drove the rating, and so decides who a person looks at and in what order | Block, clear, decline or approve a payment. It can be wrong in both directions, and a person decides |
| **The assistant** (the trained explainer rewrites the checked answer) | Explains the bank's check in plain words from the review's own facts: why it waits, how long, what the bank asked, what to prepare | Clear, decline, approve, remind or answer for the parent; change a number (the number guard checks every figure) |
| **The plain rules** | The name-list match; context for the reviewer; the fallback when the model is not loaded | Make any call about legality |

## 7. How good is the AI's reading, honestly

Measured on a later period of the data that the model never saw (`docs/AI_RISK.md` has everything):

| Routing rule | Payments sent to a person | Accuracy | Precision | Recall |
|--------------|--------------------------:|---------:|----------:|-------:|
| Medium or high (what the desk does) | 0.34% | 99.68% | 29.2% | 56.5% |
| High only | 0.15% | 99.83% | 52.7% | 45.4% |

Read this carefully: accuracy is high at every setting only because 99.8% of the data is not flagged
(answering "not flagged" every time scores 99.82%). **Precision and recall cannot both pass 90% on this
data**: where precision is 90% recall is about 13%, and where recall is 85% precision is about 1.5%. That
trade-off is a property of the data (`docs/AI_RISK.md` section 5), not of a setting. The model is a
router to a person, not an oracle.

## 8. API

| Endpoint | Who | What |
|----------|-----|------|
| `GET /bank-review/queue` | reviewer | The waiting reviews, urgency then AI reading, with the clock and stats |
| `GET /payments/{id}/bank-review` | parent, student, AI, reviewer | The plain page (parent) or the brief (reviewer), each with the AI's reading |
| `POST /payments/{id}/bank-review/decision` | reviewer, `X-MFA-Proof`, `Idempotency-Key` | `CLEAR`, `ASK_INFO` or `DECLINE` |
| `POST /payments/{id}/bank-review/reply` | parent, `Idempotency-Key` | The parent's short answer; the review reopens |
| `POST /payments/{id}/bank-review/remind` | parent, `Idempotency-Key` | A reminder, with a cool-down |

Settings: `review.*` in `config/rules.yaml`; `RISK_MODE=off` removes the model (the plain rules then
decide, and the page says so).

## 9. Try it

**The quick way:** with the API running, `python -m app.scripts.review_demo` (from `backend/`) plays the
whole story and checks each step; add `--leave-open` to stop while the payment waits for the bank, so
you can look at the screens. About two minutes (payment writes are limited to ten a minute, and it
waits as the server asks). By hand:

1. Sign in as the demo parent. An ordinary payment (for example GBP 10,000 to a university) is rated
   **low**: the page says "No bank check needed" and shows the AI's reading.
2. To see a review open, make **five quick payments to the university the family already pays, then a
   first payment to a new receiver** (GBP 2,000 five times, then GBP 8,000). The model reads a new
   receiver after a run of quick payments as unusual (`medium` or `high`), and the payment page shows
   **"Waiting for the bank"**, the AI's reading with its reasons, the target time and a checklist of
   what to have ready. A receiver whose name contains `REVIEW_TEST` (the sandbox's name-list test) also
   goes to a person, whatever the model says.
3. Ask the assistant: *"Why is my payment on hold? What will the bank ask me?"*
4. Sign in as the reviewer (`admin@demo.studyroute.test`), open **Bank review**, open the brief, choose
   *Ask for more*, give a reason and a note, and sign with the MFA code. As the parent, answer in a few
   words. As the reviewer, clear it. As the parent, approve.

## 10. Tests

`backend/tests/test_bank_review.py`, `test_bank_review_assistant.py`, `test_risk_signals.py`,
`test_risk_history.py`, `test_risk_scorer.py`, `test_risk_model.py` and
`web/components/review/review.test.tsx`, plus the accessibility checks in `web/tests/a11y.test.tsx`.
Between them: the fast lane; the gate on approval; MFA bound to the payment and single use; the AI and the
parent cannot decide; the AI reading decides routing, the name-list match still goes to a person, and
the plain rules decide only when the model is off; one decision per review; ask / answer / decline; the
clock, the reminder cool-down and the average time to decide; wording that never accuses anyone; the
reset; the answer sealed at rest; and the two ways of counting earlier payments agreeing.

## 11. What a real bank would change

The thresholds and the model's training data (a real bank would train on its own labelled history, which
is where the real gain would be), the screening against real lists, the people and their authority, the
target time, the retention of what the parent writes (here sealed in the sandbox database and shown only
to that household and the reviewer) and the regulator's reporting. None of that is claimed here.
