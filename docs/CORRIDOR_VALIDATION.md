# Bangladesh → UK tuition: source-checked validation dossier

Reviewed 17 October 2026. This is **partial documentary validation**, not a live bank quotation,
regulated payment service, successful remittance, or end-to-end corridor certification.

## Destination route is a gate, not just a cost ranking
Manchester Metropolitan University (MMU, not University of Manchester) states:
- “You should only use Flywire, the University’s official payment method, to pay any fees due”.
- “We no longer accept payment by direct bank transfer”.

Primary source: https://www.mmu.ac.uk/student-life/finance/paying-university-fees

Therefore a generic direct-SWIFT recommendation to MMU is **not a validated usable payment route**,
even if it is cheapest in the synthetic engine. Do not enter a real MMU account or present Provider A/B/C
as a real MMU option. The v2 server blocks direct-bank tuition quotes, drafts, approval requests, approvals and
submission for explicitly declared or conservatively name-recognised MMU recipients. The binding
persists after API renames. The UI offers an explicit declaration. Unknown institutions remain
UNVERIFIED: this is not an identity registry, validated bank-account ownership or a universal guard.
There is no Flywire integration; the demo recipient “University of Example” is synthetic. Real deployment is blocked until the institution,
country-of-payer options, payment method, student reference and actual quote are verified.

## Origin-side fee completeness
Islami Bank Bangladesh's public comprehensive schedule, Foreign Exchange Portfolio / student file:
- Student-file opening service charge: BDT 3,000.
- Subsequent transaction: BDT 2,000.
- Regular remittance charges apply in addition.
- NOC for study/other purpose: BDT 500 per case.

Primary source: https://www.islamibankbd.com/upload_dir/charges/Comprehensive%20Schedule%20of%20Charge.pdf

Effective date/current applicability and VAT treatment for these specific rows were **not verified**.
The document includes proposed-charge headings. These are documentary examples to reconcile with an
AD bank, not current binding prices and not injected into synthetic provider rates.

## Reconciliation procedure before claiming live savings
1. Confirm the university's current accepted route on its official portal; unknown means **not validated**.
2. Obtain timestamped, redacted quotes for the same amount received, currency, purpose and deadline.
3. Capture rate, quote expiry, file opening/renewal, transaction fee, SWIFT, intermediary/receiving charges,
   VAT/tax, charge code, reference, refund rules, cut-off and arrival estimate.
4. Determine which costs are already included. Do not double-count file fees or FX margin.
5. Compare sender debit and beneficiary net receipt separately; reject short-paying or ineligible routes.
6. Reconcile with a written bank quotation or receipt, record deviations and assumptions. No real money
   needs to be moved for the competition demonstration.

## What this release actually demonstrates
- Deterministic synthetic rate/fee arithmetic and short-payment warnings, tested independently.
- Clear “sandbox / synthetic / indicative” separation and no guarantee that OUR ensures full arrival.
- A verified real-world counterexample showing why institutional route eligibility matters.
- No live FX feed, provider partnership, Bangladesh-specific Flywire availability check, current binding
  bank fee confirmation, real student study or measured real-world savings.

The evidence JSON `submission/evidence/release/corridor_sources.json` explicitly records these gaps.
