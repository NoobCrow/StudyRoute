# Smart escrow and the audit anchor (sandbox chain)

Added 15 October 2026. Everything here is a **simulation**: the chain is an in-memory EVM inside the
StudyRoute backend, the tokens are not money, and no bank or public network is contacted. The
contracts are real Solidity, compiled and executed for real.

## 1. Why a smart contract, and why for banking

A parent paying tuition has three practical problems that a contract solves better than a form:

| Problem | What the contract does |
|---------|------------------------|
| "Will the university get its money on the date, and only then?" | Locks the funds up front and pays each **tranche** on its date. The schedule runs by itself. |
| "My child's visa was refused. Can I get the unpaid months back?" | The parent can take back every tranche that is **not yet due**. The university can send a tranche back. Neither needs a support ticket. |
| "Can the bank stop a suspicious payment without being able to steal it?" | The bank's compliance role can **freeze** and **unfreeze**, and nothing else. No function lets it move funds. |

It also fixes a weakness in the audit log. A SHA-256 hash chain catches an edited event unless an
attacker recomputes every later hash. The **AuditAnchor** contract keeps a copy of the newest hash
in the simulated EVM. Its replay history lives in the SAME SQLite database, so only an
audit-only rewrite is caught; a coordinated rewrite of both logs can pass after restart.
See [AUDIT_TRUST_BOUNDARY.md](AUDIT_TRUST_BOUNDARY.md) for the independently protected checkpoint workflow.

## 2. The pieces

```
 Parent / reviewer (browser)               FastAPI                         Sandbox chain (in memory)
 --------------------------                -------                         ------------------------
 Plan an escrow            -------->  EscrowService.plan   (no chain call)
 Lock funds (MFA, this escrow) ---->  EscrowService.confirm ---> TokenisedDeposit.mint   (bank)
                                                           ---> TokenisedDeposit.approve (parent)
                                                           ---> TuitionEscrow.create     (parent)
 (nothing: the date arrives) ------>  worker tick           ---> TuitionEscrow.releaseDue (university)
 Pay a tranche early (MFA) -------->  EscrowService.release_early -> TuitionEscrow.releaseEarly
 Cancel the rest (MFA) ------------>  EscrowService.cancel        -> TuitionEscrow.cancel
 Freeze / unfreeze (reviewer) ----->  EscrowService.freeze        -> TuitionEscrow.freeze
 Anchor the audit log (reviewer) -->  ChainService.anchor_audit   -> AuditAnchor.anchor
                                             |
                                             v
                          chain_log (SQLite, append-only, hash-chained)  <-- the chain is rebuilt
                          audit_events (same transaction, one event per state change)   from this
```

| Part | Where | Role |
|------|-------|------|
| `TokenisedDeposit` | `contracts/src/TokenisedDeposit.sol` | A bank-issued tokenised deposit, one per currency (an ERC-20 subset). Only the issuing bank mints. 1 unit = 1 minor unit. |
| `TuitionEscrow` | `contracts/src/TuitionEscrow.sol` | Locks a token for a beneficiary in up to 60 tranches. Release, refund, cancel, freeze. |
| `AuditAnchor` | `contracts/src/AuditAnchor.sol` | Append-only list of audit-log head hashes. Only the operator (the bank) writes. |
| Artifacts | `backend/app/chain/artifacts/*.json` | Compiled ABI and bytecode, committed. The backend never needs Node or a compiler. |
| `SandboxChain` | `backend/app/chain/evm.py` | The EVM (`py-evm`): deploy, send, read. One transaction is one block. |
| `ChainService` | `backend/app/domain/chain_service.py` | The hash-chained `chain_log`, replay, time control, anchoring, verification. |
| `EscrowService` | `backend/app/domain/escrow.py` | The business flow, MFA, KYC, limits, sanctions, one audit event per state change. |
| Screen | `web/components/escrow/` | "Smart escrow" in the menu. |

## 3. Who can do what

| Action | Parent | Student | Reviewer | AI |
|--------|:------:|:-------:|:--------:|:--:|
| See escrows and the chain | yes | yes | yes | no |
| Plan an escrow | yes | no | no | no |
| Lock funds (**MFA for this escrow**) | yes | no | no | no |
| Pay a tranche early (**MFA**) | yes | no | no | no |
| Cancel the rest (**MFA**) | yes | no | no | no |
| Freeze / unfreeze (a written reason) | no | no | yes | no |
| Anchor the audit log, verify anchors | no | no | yes | no |
| Move sandbox chain time forward | no | no | yes | no |
| Play "the university returns a tranche" | no | no | yes | no |

The contract enforces the same rules again on its own: `releaseEarly` and `cancel` are payer-only,
`refund` is beneficiary-only, `freeze` and `unfreeze` are compliance-only, and a frozen escrow
refuses everything. A contract test checks that the compliance wallet cannot move funds.

## 4. The flows

**Plan.** The parent picks a recipient, a purpose (tuition is one payment, living costs are monthly),
a total, a number of tranches and a first date. The engine (`engine/escrow_schedule.py`) splits the
total in integer minor units (the extra units go to the first tranches, so the parts always add up)
and dates the tranches a month apart (day 31 clamps to month ends without sticking). The plan
checks the destination is open, the currency matches the destination, the beneficiary against the
mock sanctions list, and the sandbox per-transaction cap. It stores `PENDING_CONFIRMATION` and a
plan hash. Nothing is locked.

**Lock.** A human with a fresh MFA proof *for this exact escrow* confirms. KYC must be verified.
Three transactions run: the bank issues the parent a tokenised deposit (against a simulated debit of
the parent's account), the parent allows the escrow to take it, and the escrow locks it. One audit
event (`escrow.funded`) is written in the same database transaction as the chain log. The MFA proof
works once.

**Pay on the date.** Each worker tick finds escrows with a tranche whose date has come and pays it
(`escrow.tranche_released`, actor `system`, reason `SCHEDULED`). Nobody has to ask.

**Pay early / cancel.** Both are human decisions and need MFA. `cancel` takes back every tranche that
is not yet due; due tranches stay the university's.

**Freeze.** The reviewer writes a reason (it goes in the audit log; only its hash goes on the
chain). While frozen, nothing moves: not for the parent, not for the university, not on a due date.
The date passing does not matter; unfreezing lets the schedule catch up.

**Anchor and verify.** The reviewer writes the audit log's newest hash on the chain. `GET
/chain/verify` then compares the database with every anchor. It reports `MATCH`, `MISMATCH` or
`MISSING_EVENT` for each, and `PASS`, `FAIL` or `NO_ANCHOR` overall. A test performs the attack
that the hash chain alone cannot see (edit an event, recompute every hash after it): the chain check
passes, the anchor check fails. This assumes the attacker has NOT also rewritten `chain_log`.
The coordinated-rewrite regression in `test_release_hardening.py` demonstrates this limitation.

## 5. How the in-memory chain stays correct

The EVM is memory, so history lives in the database: `chain_log` is **append-only** (triggers block
`UPDATE` and `DELETE`) and **hash-chained** (each row's hash covers the one before it). Replaying
the rows rebuilds the chain exactly: the same addresses, balances and block numbers.

* **A restart loses nothing.** The chain is rebuilt on first use.
* **A failed request leaves no trace.** A transaction only counts once its row is committed with the
  rest of the request. If the request fails after the chain moved, the next read notices the
  chain is ahead of the database and rebuilds. A test makes the audit write fail after a payment
  and shows the payment vanishes from the chain.
* **Editing the log is detected.** Each row's hash is recomputed on replay. A changed or missing row
  stops the chain (`LOG_CORRUPT`) and writes are refused.
* **Time.** Chain time is the server clock plus any sandbox offset, and never goes backwards.

## 6. What is, and is not, on the chain

On the chain: amounts in minor units, dates, wallet addresses derived from internal ids, and
hashes. **Never** a name, an account number, a BIC or a payment reference (the reference is hashed).
There are no private keys anywhere: a wallet is an address derived from a label, and the server acts
as each party only after the domain layer has authorised the human behind it.

## 7. API (sandbox only; every path is 404 in production)

| Method and path | Who | Notes |
|-----------------|-----|-------|
| `GET /escrows`, `GET /escrows/{id}` | parent, student, reviewer | Tranche states come from the chain. |
| `POST /escrows` | parent | Idempotency-Key. Plans only. |
| `POST /escrows/{id}/confirm` | parent | Idempotency-Key, `X-MFA-Proof` (scope `confirm_escrow`). |
| `POST /escrows/{id}/tranches/{i}/release` | parent | Idempotency-Key, MFA (`release_escrow`). |
| `POST /escrows/{id}/cancel` | parent | Idempotency-Key, MFA (`cancel_escrow`). |
| `POST /escrows/{id}/abandon` | parent | Drops a plan that was never confirmed. |
| `POST /escrows/{id}/freeze`, `/unfreeze` | reviewer | `{"reason": "..."}`, 3 to 120 characters. |
| `POST /escrows/{id}/tranches/{i}/sandbox-refund` | reviewer | Plays the university returning a tranche. |
| `GET /chain/status`, `GET /chain/anchors` | all signed-in humans | Contracts, addresses, log head, integrity. |
| `POST /chain/anchor` | reviewer | Writes the audit head on the chain. |
| `GET /chain/verify` | reviewer | Compares the database with every anchor. |
| `POST /chain/sandbox/advance` | reviewer | `{"days": n}`. Then pays what is due. |

## 8. Rebuilding the contracts

```bash
cd contracts && npm ci && npm run build   # writes backend/app/chain/artifacts/*.json
```

`solc` 0.8.37 (the `solc` npm package, WebAssembly, no download), `evmVersion: paris`. CI rebuilds
and fails if the committed artifacts differ. `backend/tests/test_chain_contracts.py` also checks each
artifact against its source file by SHA-256.

## 9. Tests

* `test_chain_contracts.py` (30): access control, every revert reason, the compliance freeze, and a
  random sequence of 300 operations proving the escrow always holds exactly what is still locked.
* `test_chain_service.py` (16): replay after restart, rollback recovery, tamper detection, time
  travel, anchoring, and the consistent-rewrite attack.
* `test_engine_escrow_schedule.py` (14): the split, month-end dates, impossible schedules.
* `test_api_escrow.py` (32): the whole flow through the API, RBAC (including the AI), MFA binding,
  idempotency, one audit event per state change, no personal data on the chain, production 404.
* Frontend: `Escrow.test.tsx` and two axe tests; a real-browser run checks the same screen with
  colour contrast, in light and dark, on desktop and phone.
* `demo_flow` step 13 walks the full story against a running API.

## 10. Limits and honest caveats

* **Not a real network.** One process, no peers, no consensus. The value of a real chain (shared
  state between banks) is not simulated; this shows the contract logic and the controls.
* **Tokens are not money.** The bank "issues" a token against a simulated debit. The Bank network
  screen is a separate simulation and is not linked to this one.
* **Gas, fees and keys are not modelled.**
* **Portability is untested.** The contracts use Solidity `>=0.8.11 <0.9.0` and the `paris` EVM, which
  should run on other EVM-compatible chains, including consortium chains. This has **not** been
  tried; treat it as a next step, not a claim.
* **SQLite triggers can be dropped by someone with file access.** The hash chain (and, for the audit
  log, the anchor) is what detects that.
* **Anchors are only as fresh as the last anchoring.** Events after the newest anchor are covered by
  the hash chain alone. Anchor before a demo and before submitting.
* **Open questions** for a real deployment are in [OPEN_QUESTIONS.md](OPEN_QUESTIONS.md) section C.
