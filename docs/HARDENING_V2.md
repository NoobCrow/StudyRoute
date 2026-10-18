# StudyRoute hardening v2

This is a bounded engineering improvement, not a claim of 85 points, production readiness or a
competition outcome. The earlier release evidence remains in `submission/evidence/release/` as a
historical baseline; current v2 verification is in `submission/evidence/v2/`.

## University route protection

Official source reviewed on 2026-10-17:
https://www.mmu.ac.uk/student-life/finance/paying-university-fees

Manchester Metropolitan University states that Flywire is its official fee payment method and direct
bank transfers are no longer accepted. The configured policy covers self-funded university tuition,
not International College. These facts are not a current Flywire quotation or Bangladesh-payer check.

Implementation:
- Optional `institution_id` on `POST /api/v1/recipients`. Current catalogue contains only
  `gb-manchester-metropolitan`. Invalid declarations/country/type combinations are rejected.
- Explicit UI declaration and conservative full-name recognition; a bare “MMU” is not treated as
  identity evidence. University of Manchester is not Manchester Metropolitan University.
- Additive `recipient_institutions` table: no alteration/deletion of old encrypted data. A binding
  survives renaming; existing recognised names are bound before API rename.
- Blocks direct-bank **TUITION** quotes, draft creation, approval requests, approvals and system
  submission. An unbound generic quote cannot bypass the draft guard. Legacy payments are rechecked.
- Denials have a source-backed reason and audit event, without creating the draft/quote or advancing
  the payment. Read-only blockers reflect the policy without mutating it.
- `GET /api/v1/institutions` and `/api/v1/recipients/{id}/route-policy` require authenticated access;
  recipient ownership applies. Unknown recipients return `UNVERIFIED`, never “accepted”.
- Recipient deletion cascades only its institution binding, consistent with household reset.

Trust limitations:
- This is a **small configured policy guard**, not identity/account verification. An arbitrary alias
  with no declaration can evade recognition. Bank-network/escrow simulations are not certified
  institution-payment integrations. Do not claim universal prevention of incorrect bank transfers.
- No Flywire integration, no live quote, no licensing opinion, no real funds. Unknown recipients can
  use synthetic comparisons, not validated real payments.
- The catalogue is pinned to the review date and must be reviewed against current official instructions
  before real use. A change in policy requires a reviewed code/config update; no auto-trust of scraped text.

## New synthetic intent challenge

Run `python ml/review_challenge.py` from repository root with backend dependencies installed.

Dataset: `ml/data/review_challenge_v2.jsonl`, 60 English context-free cases. Gold labels and dataset
hash were frozen before its first model run. No model weights, thresholds, attack policies or gold
labels were tuned to this result. Complete predictions, including errors, are published.

Observed: agent 54/60 intent routes correct; rules baseline 51/60. Eight attack cases: agent
blocked 8/8, baseline 7/8. This small curated comparison does not establish statistical superiority.
Retained agent errors include safe draft/approval wording overblocked as ATTACK, a payment-state
explanation routed to HELP, a sandbox-boundaries question routed to LIMITS, and football routed
to STATUS. The model was not tuned to repair these challenge cases.

This is AI-authored synthetic challenge evidence, **not independent evaluation**, a user study or
representative real-world accuracy. It measures intent routing only, not financial correctness,
multi-turn task execution or cloud LLM safety. Wilson intervals in JSON assume binomial trials and
must not be mistaken for population generalisation with curated/nonrandom examples.

## Remaining high-value human evidence

1. Revoke exposed original credentials at the provider; source sanitation cannot revoke tokens.
   Preserve/re-encrypt deployed encrypted data safely when rotating encryption keys.
2. Obtain same-amount, same-deadline written quotes for one genuinely accepted institution route.
   Reconcile sender debit, beneficiary receipt, file fees, tax, intermediary charges and expiry.
3. Run the consented usability procedure in `docs/VALIDATION_PROTOCOL.md`; publish failures as well as
   successes. No participant or savings result is supplied by this release.
4. Test the chosen cloud LLM separately with a non-production key and cost/privacy limits. Offline
   template-reader probes do not establish cloud-provider safety or autonomous financial reasoning.
5. Perform a clean-machine dependency installation and Docker/deployment smoke test. This environment
   reuses installed dependencies. Local API/UI verification does not prove a remote deployment.
6. Confirm team eligibility, authorship, judging access and current official submission instructions.


## Security probe interpretation

The local two-household lab uses synthetic users and a loopback HTTP service with rate limits off
for functional probes. Those settings must not be copied to a public deployment. The API/assistant
probes, leak scan, request-replay tests and production-CSP browser audit are developer-run checks,
not an independent penetration test or an exhaustive proof of safety.

The MITM probe retains four informational findings: plain HTTP exposes credentials/tokens; a captured
bearer token can read a household's data until expiry and can cancel a pending draft. TLS is mandatory
outside loopback, short token expiry limits but does not eliminate theft, and MFA protects approval
rather than every read/cancel operation. No real account or real credential was used for this lab.
