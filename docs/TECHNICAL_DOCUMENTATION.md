# StudyRoute: technical documentation

International Track, Topic C: Cross-border and Student Finance Assistant.
Covers the three items the rules ask for: **system architecture**, **core algorithm description**
and **security design**.

> StudyRoute is a sandbox. No real money moves and all data is synthetic. Guidance is indicative:
> confirm with your Authorised Dealer (AD) bank.

**Design principle.** The engine calculates, the AI explains, the human approves, and every step is
logged. Each part below exists to make one of those four statements true and testable.

---

## 1. System architecture

### 1.1 Components

```
 Browser (React + TypeScript)
        |  same origin, strict CSP
        v
     nginx  --- serves the built UI, proxies /api, sets X-Forwarded-For
        |
        v
 FastAPI  (security middleware: request id, size limit, headers, X-Sandbox)
   |   auth (JWT ES256) - RBAC - rate limit - schema validation - Idempotency-Key - RFC 7807 errors
   |
   +--> Engine    pure functions: money, FX margin, fees, ranking, planner, runway, MT103 preview
   +--> Domain    state machine, KYC gate, limits, sanctions check, recipients, documents, rules
   +--> AI layer  policy check, facts, masking, model client (optional), number guard, tool guard
   +--> Audit     append-only hash chain, verify
   +--> Providers mock adapters A, B, C  -->  simulator  -->  HMAC-signed webhooks back to the API
   |
   v
 SQLite (Postgres optional), foreign keys on, CHECK constraints, audit triggers
```

| Layer | Folder | Responsibility | I/O |
|-------|--------|----------------|-----|
| Engine | `backend/app/engine/` | Every number: costs, ranking, deadline, runway | None (pure) |
| Domain | `backend/app/domain/` | State machine, guards, RBAC, KYC, limits, config | Database via a passed-in session |
| API | `backend/app/api/` | Routes, authentication, idempotency, rate limits, errors | HTTP |
| Audit | `backend/app/audit/` | Hash chain and verification | Database |
| Providers | `backend/app/providers/` | Mock providers, simulator, webhook signing | HTTP (webhooks) |
| AI | `backend/app/ai/` | Orchestrator, masking, number guard, tools, templates | Optional network call to a model |
| Web | `frontend/src/` | Dashboard, compare, recipients, documents, payment, audit, rules, sandbox, chat | HTTP |

The engine has no database, clock or network access, so it is fully unit-testable and its output
can be trusted as the single source of numbers.

### 1.2 Data model

`users`, `recipients` (account stored encrypted with AES-256-GCM, only the last four digits shown),
`quotes` (inputs, results, mid-rate source and time, input hash), `payments` (state, summary hash,
version for optimistic locking), `payment_transitions`, `audit_events`, `audit_head`,
`idempotency_keys` (unique per user and key), `webhook_events` (unique event id), `config_rules`
(value, source URL, last checked, verified), `kyc_records`, `documents`, `mfa_proofs`,
`refresh_tokens`, `provider_ledger`. The payment state is limited by a CHECK constraint, and two
triggers block `UPDATE` and `DELETE` on `audit_events`.

### 1.3 Payment lifecycle

```
DRAFT -> QUOTED -> PENDING_APPROVAL -> APPROVED -> SUBMITTED -> SETTLED
            |            |                |             |-----> FAILED
            |            |-> REJECTED     |-> CANCELLED
            +--- quote expires: QUOTED or PENDING_APPROVAL returns to DRAFT
```

It is a transition table: every row names the event, the allowed source states, the target state,
**who may trigger it** (parent, AI, admin, system, provider) and the guards that must hold. An
illegal move returns `409 INVALID_STATE`. Each transition writes exactly one audit event in the same
database transaction, and an optimistic-lock version column stops two simultaneous approvals from
both succeeding.

Approval guards: quote still valid, KYC verified, recipient allowlisted, mock sanctions check clear,
sandbox per-transaction and daily caps respected, a fresh MFA proof, and the hash of the approval
summary the human saw. `APPROVE` is allowed to a human parent only; the AI actor gets
`AI_CANNOT_APPROVE`.

### 1.4 Request path and the agent loop

1. The parent compares providers, creates a draft and requests approval. The assistant can explain
   any number and can *propose* a draft or an approval request, but a person clicks each step.
2. Requesting approval freezes a summary (recipient, amount, rate, charge code, total cost, latest
   send date, quote expiry) and stores its SHA-256.
3. The parent approves with `X-MFA-Proof` and `confirm_summary_hash`. If anything changed, the hash
   differs and the approval is refused.
4. A background worker submits the approved payment after a short cancellation window, assigns a
   UETR (UUID v4) and hands it to the mock provider. The simulator later sends an HMAC-signed
   webhook; the API verifies it and applies `SETTLED` or `FAILED`.

---

## 2. Core algorithms

### 2.1 True total cost (the comparator)

Convention: every rate is **BDT per 1 unit of foreign currency**. A provider selling foreign
currency quotes above mid-market; the gap is the hidden margin. For one provider, with target
amount `T` (foreign), mid rate `m` and provider margin `g` percent:

```
provider_rate      = m * (1 + g/100)                         (six decimals)
fx_cost_bdt        = (provider_rate - m) * T
if charge_code == OUR:   sender_extra_bdt = (intermediary_fee + receiving_fee) * m ; shortfall = 0
else (SHA or BEN):       sender_extra_bdt = 0 ; shortfall_foreign = intermediary_fee + receiving_fee
                         (BEN also deducts the provider's fixed fee from the beneficiary)
shortfall_bdt      = shortfall_foreign * m
total_cost_bdt     = fx_cost + fixed_fee + swift_fee + sender_extra + shortfall_bdt
cost_pct           = total_cost_bdt / (T * m) * 100
parent_pays_bdt    = T * provider_rate + fixed_fee + swift_fee + sender_extra
```

Providers are ranked by `cost_pct`, then by what the parent pays, then by provider id, so the order
is deterministic. A provider that cannot offer the requested charge code is quoted with its default
one, and the result carries both `requested_charge_code` and `charge_code` plus a warning.

**Worked example (synthetic, GBP 10,000, mid rate 160.00):**

| Provider | Rate | Fixed + SWIFT | Charge | Shortfall | Total cost | Cost % | Parent pays |
|----------|------|---------------|--------|-----------|------------|--------|-------------|
| B | 161.60 | 3,000 + 1,500 | OUR (GBP 30 intermediary) | 0 | BDT 25,300 | 1.58% | BDT 1,625,300 |
| C | 162.00 | 500 + 0 | SHA (GBP 25 + 10 deducted) | GBP 35 | BDT 26,100 | 1.63% | BDT 1,620,500 |
| A | 163.20 | 1,500 + 1,000 | OUR (fees bundled) | 0 | BDT 34,500 | 2.16% | BDT 1,634,500 |

B ranks first, C second with a red shortfall warning (the university would receive GBP 9,965), A
third. This is blueprint test T01 and the demo uses it.

**Numeric rules.** Money is an integer count of minor units plus a currency code, never a float.
Rates are `Decimal`. Each money part is rounded **once**, half-up, at the end. Zero, negative and
unsupported amounts are rejected with `422 VALIDATION_FAILED`.

### 2.2 Quote lifecycle

A quote stores every input, the mid-rate source and timestamp, and an input hash. It expires after
300 seconds (configurable). Approving with an expired quote returns `409 QUOTE_EXPIRED` and sends
the payment back to DRAFT; the parent requotes with the same provider.

### 2.3 Deadline planner

A **business day** is a day that is a working day in *both* Bangladesh (Friday and Saturday off)
and the host country (own weekend and holidays), from configuration.

```
latest_send_date    = due_date stepped back (settlement_days + buffer_days) business days
recommended_send    = latest_send_date stepped back one more business day
earliest_send_today = today if business day and before the bank cut-off, else the next business day
status:  ON_TRACK  if earliest <= recommended
         TIGHT     if earliest <= latest        (using the buffer)
         AT_RISK   if earliest <= latest_without_buffer
         LATE      otherwise
```

Every skipped day is returned with its reason (for example "BD weekend" or "GB holiday: ...") and
shown in the UI, plus warnings for pending KYC and expired quotes. A scan limit stops a
mis-configured calendar from looping forever.

### 2.4 Living-cost runway and synthetic rate hint

Runway reports the whole months an amount covers and the leftover (integer division of minor
units), plus a one-decimal figure that is rounded **down** so it never over-promises. The rate hint compares today's synthetic rate with its recent average and says
"today looks better", "about average" or "waiting may help". It is labelled synthetic and
indicative, and is not a forecast.

### 2.5 The AI pipeline

```
 user message --> 1 policy check --> 2 facts from the engine --> 3 mask personal data
              --> 4 model (optional) --> 5 number guard --> 6 tool guard --> 7 un-mask --> 8 audit
```

1. **Policy check.** Pattern rules flag instruction overrides, action requests (approve, send, pay,
   cancel), limit and config changes, privilege claims, secret requests and requests to invent
   numbers. A flagged message gets a fixed refusal, the model is **not called**, and an
   `ai.blocked` audit event is written. Document text goes through the same check.
2. **Facts.** The orchestrator builds a numbered list of facts from engine output only
   (`fact_17 = "Provider B cost %": "1.58%"`).
3. **Masking.** Names become `[PERSON_n]`, IBANs and long digit runs become `GB** **** 4821`
   style tokens, passports, e-mails and phones are removed and never restored. The mapping stays on
   the server and is used to un-mask the reply.
4. **Model.** Optional. A provider-agnostic client (Anthropic or an OpenAI-compatible endpoint)
   receives the system prompt, the masked facts and the masked message, and must answer in JSON
   with the ids of the facts it used. The model id is pinned by the operator and logged.
5. **Number guard.** Every number in the reply is extracted with a regular expression that ignores
   identifiers such as `fact_17`, normalised to a `Decimal`, and must equal a number in the allowed
   facts. Any other number fails the reply, which is retried once and then replaced by a
   deterministic **template answer** built from the same facts.
6. **Tool guard.** The model may only propose `create_draft` or `request_approval`. Reads are done
   by the orchestrator. Approve, submit, cancel, change limit, allowlist and edit config are not
   available to the AI, and each proposal must pass the same permission check as a human call.
7. **Audit.** One event records the prompt hash, output hash, model version and guard result.

With no model key the assistant runs in **template mode**: the same pipeline without step 4. The
UI shows a "Template mode" badge, so the demo never depends on a network.

### 2.6 Audit hash chain

```
GENESIS             = "0" * 64
canonical(e)        = JSON of e without this_event_hash, keys sorted, no whitespace, UTF-8
this_event_hash(e)  = SHA256( prev_event_hash + canonical(e) )
verify:  prev = GENESIS
         for e in events ordered by seq:
             fail at e.seq if e.prev_event_hash != prev
             fail at e.seq if SHA256(prev + canonical(e)) != e.this_event_hash
             prev = e.this_event_hash
```

Appending locks the head row, so concurrent writers keep one linear chain. `GET /audit/verify` can
also compare the head with a hash published outside the database, which detects truncation. The
chain is tamper-evident, not tamper-proof.

### 2.7 Idempotency

Every payment write needs an `Idempotency-Key` (UUID). The key, a hash of method, path and body, and
the response are stored in the **same transaction** as the change, for 24 hours. The same key and
body replays the stored response with `Idempotent-Replay: true` and no second effect. The same key
with a different body returns `422 IDEMPOTENCY_KEY_REUSED`. A unique constraint on (user, key)
makes two simultaneous requests safe.

### 2.8 Webhook verification

```
signature = HMAC_SHA256(secret, timestamp + "." + raw_body)      header: t=<ts>,v1=<hex>
```

The receiver reads the **raw** body first, rejects a timestamp more than 300 seconds old (replay),
recomputes the HMAC for the current and the previous (rotation) secret of each provider and compares
in constant time, then de-duplicates by `X-Event-Id`, and only then parses the JSON and applies the
transition. Each rejection writes a `webhook.rejected` audit event and changes nothing.

### 2.9 MFA step-up

A fresh proof is required to approve a payment and to allowlist a recipient. It is valid 5 minutes,
single use, and bound to the user, the scope (`approve_payment` or `allowlist_recipient`) and the
object id, so a proof for one payment cannot approve another. TOTP (RFC 6238) works in every mode;
sandbox mode also accepts a documented fixed code so judges need no authenticator app.

---

## 3. Security design

The full threat and control matrix, with the test that proves each row, is in
[SECURITY.md](SECURITY.md). The permission tiers and the known-risk list are in
[SECURITY_SELF_ASSESSMENT.md](SECURITY_SELF_ASSESSMENT.md). Summary:

| Concern | Design |
|---------|--------|
| Authentication | Argon2id passwords; ES256 access tokens (15 minutes); rotating refresh tokens with reuse detection; lockout after repeated failures; MFA step-up for approval and allowlisting |
| Authorisation | Role and token-scope checks in the domain layer; ownership checks return 404; the AI service account has its own scope list with no approve, cancel, reject, limit or config permission |
| Integrity of money | Integer minor units; summary hash bound to approval; idempotency; optimistic locking; one audit event per transition in the same transaction |
| Provider trust | HMAC-signed webhooks with timestamp window, secret rotation and event de-duplication |
| AI safety | Policy check, masking, number guard, tool allow-list, human approval, template fallback |
| Data protection | AES-256-GCM for account numbers; masked display; log redaction filter; personal data masked before any model call; "Reset my data" |
| Web | Strict CSP with no inline script or style; `nosniff`; `Referrer-Policy: no-referrer`; frame-ancestors none; HSTS; exact-origin CORS without credentials; bearer tokens in memory only |
| Abuse | Per-IP and per-user rate limits, request size limit, schema validation that rejects unknown fields |
| Compliance | Rules in configuration with `source_url`, `last_checked` and a `verified` flag; yellow "Not verified" badge and "Indicative. Confirm with your AD bank." for anything unchecked; mock KYC gate; mock sanctions check; travel-rule fields in the instruction preview |
| Sandbox honesty | `X-Sandbox: true` on every API response and a banner on every screen; every simulated part labelled; no claim of a live bank or FX feed |

## 4. Verification

- `backend/tests/` has one or more tests for each blueprint scenario T01 to T24 and fails if one
  is missing; see [TEST_CASES.md](TEST_CASES.md).
- `python -m app.scripts.demo_flow` replays the ten-step demo against a running API and prints
  OK or FAIL for each check.
- Operation logs from a real run are in `submission/evidence/`.
- `python scripts/scan_repo.py` and the CI workflow scan for secrets, real e-mails and TODOs.
