# The sandbox bank network

StudyRoute can show how money really moves from one bank to another, at home and abroad, using
**invented banks and synthetic accounts**. Open the **Bank network** screen after signing in.

> **Everything here is simulated.** The banks, BIC-style codes (all start with `EXMP`), account
> numbers, fees, limits and timings are made up for the sandbox (`config/bank_network.yaml`). No real
> bank, scheme or regulator is contacted or described, and none of the numbers is verified against
> one. The screen and every API response say so.

## What you can do

| You do | What the sandbox shows |
|--------|------------------------|
| Send BDT from your account to a cousin at the **same bank** | One step: the bank books it to its own customer. Free |
| Send BDT to a relative at **another Bangladesh bank** | Three hops through a **clearing house**: sending bank, clearing house, receiving bank. Pick an instant, next-batch or high-value rail, or let the sandbox pick the cheapest that accepts the amount |
| Send GBP inside the UK (student account to the university) | The same three hops through the UK clearing house |
| Send BDT to a **university abroad** | Three hops over **SWIFT through a correspondent bank**: your bank sells the currency and pays out of its nostro account, the correspondent forwards through its own nostro, the university's bank credits the customer. An MT103 message (simulated) travels with the first two hops |

The screen also adds up the household's money in every currency (the parent's Bangladesh accounts and
the student's UK account), with an indicative BDT total at the synthetic mid-market rates. That is the
multi-currency view; it is a guide, not a live rate.

Every transfer has a plan first (fees, what the beneficiary receives, every hop), then you confirm
it with MFA, then the banks move it one hop at a time while you watch.

## The banks

| Code | Name (all invented) | Role |
|------|---------------------|------|
| `EXMPBDA1`, `EXMPBDB1`, `EXMPBDC1` | Example Bank A, B, C | Bangladesh banks. Their prices are Provider A, B and C of the Compare screen |
| `EXMPUS6C` | Example Correspondent Bank | Sits between a Bangladesh bank and the foreign bank |
| `EXMPGB2L`, `EXMPGB2X` | University Bank of Example, Sample Bank London | UK banks (the university banks with the first) |
| `EXMPUS33`, `EXMPDEFF`, `EXMPAU2S`, `EXMPCATT`, `EXMPMYKL` | Example Banks US, Germany, Australia, Canada, Malaysia | One host bank for each of the other corridors |
| `CLR-BD`, `CLR-GB` | Sandbox Clearing Houses | Settle between banks of one country |

Seventeen synthetic customer accounts are created: the parent's three Bangladesh accounts, the
student's UK account, a cousin, a relative and an aunt, a landlord, six universities, and three
accounts that trigger the test scenarios.

## How the books work

Every posting is **double entry**: a journal lists debits and credits, and for each currency the
debits equal the credits. A customer deposit is a liability (a debit lowers it), a nostro account is
an asset, and so on. Money is integer minor units, never a float.

A worked example, GBP 10,000 to the university with charge code OUR, Provider A (rate 163.20,
fixed fee BDT 1,500, SWIFT fee BDT 1,000):

| Step | Who | Posting |
|------|-----|---------|
| Reserve | Bank A | Debit the parent's account **BDT 1,634,500.00**, credit "in flight" |
| Hop 1 | Bank A | Debit in flight 1,634,500.00. Credit fee income 2,500.00. Credit BDT position 1,632,000.00. Debit GBP position 10,000.00. Credit its **nostro** at the correspondent GBP 10,000.00 |
| Hop 2 | Correspondent | Debit the **vostro** Bank A keeps there GBP 10,000.00. Credit its own nostro at the university's bank GBP 10,000.00 (and its fee income if there is a lifting fee) |
| Hop 3 | University's bank | Debit the vostro the correspondent keeps there. Credit the **university's account GBP 10,000.00** (and its fee income if there is a receiving fee) |

The number the parent pays equals the Provider A figure on the Compare screen, because the plan
reuses the fee engine's result and checks it (a test compares them for every provider and charge
code). With OUR the university receives the full amount; with SHA or BEN the charges are taken from
it, exactly as the quote warned.

**Mirror accounts.** A nostro ("our account at your bank") and the matching vostro ("your account at
our bank") must always show the same balance. The screen's **Do the books balance?** card checks
that, the trial balance of every currency, and that no stored balance differs from the sum of its
entries (so a balance edited behind the ledger's back is caught, like the audit chain).

**A failed transfer is unwound exactly.** If the beneficiary's bank rejects the payment (a
beneficiary named `FAIL_TEST`), or a bank lacks liquidity, the sandbox posts the exact opposite of
every journal so far, newest first. The parent gets back everything, fees included, and the books
still balance. Real banks usually keep some fees on a return; the sandbox does not.

The ledger is **append-only**: journals and entries cannot be updated or deleted (SQLite triggers),
and a correction is a reversing journal.

## Controls (the same rules as payments)

| Rule | How it applies |
|------|----------------|
| The AI never moves money | The AI has no bank permission at all. Only a parent can plan, confirm or cancel |
| A human with a fresh MFA proof | Confirming needs an MFA proof bound to **that transfer** (scope `confirm_bank_transfer`). A proof for another transfer, or for a payment, is refused; a proof works once |
| Idempotency | Planning and confirming need an `Idempotency-Key`. A retry replays the first answer and never creates or confirms twice |
| Audit | Every state change writes one audit event in the same transaction: created, confirmed, each hop, settled, returned, blocked, cancelled |
| KYC | An international transfer needs verified KYC (simulated) |
| Screening | A beneficiary whose name contains `SANCTION_TEST` is blocked before any money moves, and the block is audited |
| Caps | International transfers respect the sandbox per-transaction cap (our own number, not a legal limit). Each rail has its own minimum and maximum |
| Roles | Student and reviewer can look; the reviewer can also run the next hop or force a failure (audited) |
| Rate limits | Bank writes have their own limit (20 a minute per user) |
| Sandbox only | In production mode every bank path answers 404 |

## Try it

| Type this beneficiary | What happens |
|-----------------------|--------------|
| `FAIL_TEST University` (UK) | Goes through all hops, then the university's bank rejects it and everything is returned |
| `SLOW_TEST Rentals` (UK, same bank as the student) | Every delay is six times longer |
| `SANCTION_TEST Trading` (UK) | Blocked by the mock screening |
| Any amount above the student's GBP 800.00 | Planning works, confirming is refused: not enough funds, and nothing changes |

Timings (simulated): same-bank 1 second; instant rail about 3 seconds; next-batch rail about 26
seconds (it waits for its batch window); international about 12 seconds.

From the command line (the reviewer account can also move a transfer by hand):

```bash
docker compose exec backend python -m app.scripts.demo_flow     # step 12 is the bank network
```

## API

All under `/api/v1/bank`, sandbox only. Money is `{amount_minor, currency}` plus a formatted string.

| Method and path | Who | What |
|-----------------|-----|------|
| `GET /network` | any signed-in role | Banks, rails, trial balance, mirror accounts, `all_ok` |
| `GET /accounts` | parent, student, reviewer | Customer accounts with balances (the household's own; all for the reviewer) and, for a household, `totals` by currency with a BDT equivalent |
| `GET /beneficiaries` | same | Every customer account a transfer could go to, without balances |
| `GET /accounts/{id}/statement` | same | Entries with running balances |
| `POST /transfers` | parent | Plan a transfer. Needs `Idempotency-Key`. Moves nothing |
| `POST /transfers/{id}/confirm` | parent | Reserve the funds and start. Needs `Idempotency-Key` and `X-MFA-Proof` |
| `POST /transfers/{id}/cancel` | parent | Cancel before confirming |
| `GET /transfers`, `GET /transfers/{id}` | parent, student, reviewer | Status, hops, simulated messages, journals |
| `POST /transfers/{id}/sandbox-step` | reviewer | `{"outcome": "advance"}` or `{"outcome": "fail"}` |

## What is not simulated, and the known limits

- **Not real.** The banks, rails, fees, limits and timings are invented. They resemble the shape of
  real systems (instant, next-batch and high-value rails, SWIFT through a correspondent) and nothing
  more. Nothing is checked against a real scheme; see `docs/OPEN_QUESTIONS.md`.
- **One direction abroad.** International transfers go from a Bangladesh bank in BDT to a foreign
  account in its own currency, through one correspondent. Inbound and foreign-to-foreign transfers
  are refused with `ROUTE_NOT_SUPPORTED`.
- **Returns are exact.** No return fee, no partial return.
- **One household.** The parent can pay from any account of the demo household, including the
  student's UK account. Third parties are only beneficiaries.
- **No daily total** for bank transfers, only the per-transaction cap and the rail limits.
- **Configuration is a file.** `config/bank_network.yaml` is read at start-up; it is not edited
  through the Rules screen.
- **Not connected to payments.** A StudyRoute payment is still settled by the simulated provider;
  the bank network is a separate simulation that uses the same pricing. Linking the two is a next
  step.

## How it was checked

- Pure engine tests: balanced journals, every rail limit, and for each of Provider A, B, C and each
  charge code that the bank plan equals the fee engine (`tests/test_engine_interbank.py`).
- Ledger tests: overdraft refusal changes nothing, reversals restore every balance, mirror and
  entry checks, append-only triggers (`tests/test_ledger.py`).
- API tests: national and international flows end to end with the worker and a fake clock, failure
  and unwind, screening, MFA binding and single use, idempotency, roles, rate limit, audit chain
  (`tests/test_api_bank.py`, `tests/test_bank_setup.py`).
- A live run in headless Chrome behind the production content security policy: national, international,
  rejected, screened, phone width and the reviewer's view, with no console error.
- The 13-step demo script and the evidence export include the bank network
  (`submission/evidence/bank_network.json`).
