# Pre-registered validation protocol — not completed results

Do not fill this document with invented participants, quotes or pass rates. It is a reproducible
plan for the evidence engineering alone cannot provide. Sandbox only; no real money or identity
uploads. Record consent, remove names and never publish account numbers or credentials.

## A. One real corridor / institution

Before testing: record an official institution page, review time, scope, supported payer country and
accepted method. Exclude any direct-bank comparison if the institution requires another route.
Use the same beneficiary net amount, currency and due date for all eligible comparisons.

For each quote, collect privately and redact before release:
- Anonymous quote ID; provider; capture time/timezone; expiry; source document hash.
- Institution route eligibility and whether a Bangladesh payer is supported.
- Beneficiary target/net receipt; sender currency/debit; FX rate; rate reference/time.
- File opening/renewal, transaction, SWIFT, intermediary/receiving, VAT/tax and refund costs.
- OUR/SHA/BEN or method-specific terms; cutoff, holidays, arrival estimate and uncertainty.
- Which costs are already included; separate initial and subsequent-transfer cases.

Pass criteria: every ranked route is eligible; all arithmetic reproduces to currency minor units;
unknown charges/rates are disclosed, not zero-filled; no savings claim without matched eligible
quotes and a complete fee basis. Store disagreements, not just a favourable screenshot.
No real transfer is needed. A written quotation is not proof of settlement.

## B. Consented usability pilot

Suggested small exploratory sample: 5–8 students/parents planning tuition payments. This is not a
statistically representative study. Do not collect passports, personal bank data or real passwords.
Freeze tasks and acceptance criteria before recruiting; use synthetic accounts and randomise the
order of manual-checklist and StudyRoute conditions to reduce learning effects.

Tasks:
1. Find the sender cost for an invoice under a declared synthetic rate and identify hidden margin.
2. Explain SHA short-payment risk and why OUR is not a universal full-arrival guarantee.
3. Identify a university requiring Flywire and refuse an invalid direct-bank option.
4. Find a latest send date and name at least one cutoff/holiday assumption.
5. Create a draft without confusing it with approval or actual settlement.

For each anonymous participant/condition/task, record: start/end, success/partial/fail, assistance,
error category, whether they thought real money moved, understanding of the route restriction,
and a short optional usability comment. Consent withdrawal must remove their raw record.

Report denominators and failures. Median task time is descriptive, not evidence of population-level
savings or superiority. Do not combine correct answers produced with assistance with unassisted
success. No claim of production adoption from this pilot alone.

## C. Cloud-model gate

Use synthetic facts, a dedicated limited key and explicit budget; do not reuse exposed credentials.
Repeat hostile-prompt probes, invented-number checks, tool allowlist/role checks, stale-fact tests,
upstream error/timeouts and cross-household isolation. Capture model/provider/version and run date.
A fluent answer must not authorize payments. Record cost, latency, grounded-fact checks and failures.

## D. Release gate

From a fresh machine or disposable CI environment: install locked dependencies, run backend/frontend
suites, build UI with production CSP, scan source, build clean archive, verify every manifest hash,
start fresh sandbox, exercise one valid draft and one blocked institution route. Record exact
commands, environment, durations and exit codes. Docker remains unverified until actually executed.
