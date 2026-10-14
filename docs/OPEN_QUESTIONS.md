# Open questions and things not done

Written 14 October 2026. Nothing here is hidden: if it is not verified or not built, it is listed.
Rule of the project: when a rule or number is uncertain it goes into `config/rules.yaml` with
`verified: false` and appears here. The app shows a yellow **Not verified** badge on each of them
and says "Indicative. Confirm with your AD bank."

## A. Competition facts the team must confirm (blueprint section 18)

| # | Question | Where to check | Status |
|---|----------|----------------|--------|
| 1 | Deadline 20 Oct 2026, 23:59 Beijing (21:59 Dhaka). Internal target: evening of 19 Oct. | Official site | Confirmed by several pages, re-check once |
| 2 | Exact submission deliverables (code, report, slides, video, length) | Rules PDF, Appendix 2 for the International Track | **Open.** The submission pack in `submission/` covers all likely items |
| 3 | Scoring rubric and weights (security reported as 30%) | Rules PDF | **Open** |
| 4 | Is there a mandatory API, dataset or test environment? | Rules PDF, organiser email | **Open.** Our API (blueprint section 8) is our own design |
| 5 | Eligibility: 60% non-Chinese, full-time overseas enrolment, passport pages at registration | Rules PDF, registration form | **Open, team lead** |
| 6 | Is a demo video required or optional? | Rules PDF | **Open.** Record one anyway (script in blueprint 19) |

## B. Regulatory values kept as `verified: false`

None of these may be presented as a legal limit. They are placeholders for the AD bank to confirm.

| Config key | What it holds | Why it is unverified |
|------------|---------------|----------------------|
| `bangladesh_rules.living_expense_usd_per_month` | USD 2,000 a month | Secondary source only (LegalSeba, 2025) |
| `bangladesh_rules.living_expense_high_cost_uplift_pct` | Up to 50% more with proof | Secondary source only |
| `bangladesh_rules.single_ad_branch_rule` | `unknown` | An older circular; may be outdated |
| `bangladesh_rules.education_remittance_circular_2026_09_30` | Circular of 30 Sep 2026 | Only fragments seen. Read it in full before quoting any limit |
| `bangladesh_rules.international_card_for_education` | International cards for education spend | News report (Aug 2026) only |
| `bangladesh_rules.iso_purpose_code` | Purpose code in the instruction preview | Not stated until checked against the ISO 20022 external code list. The MT103 preview says so |
| `engine.bank_cutoff_local` | 15:00 Dhaka cut-off | Assumed. Each AD bank sets its own |
| `kyc.required_documents` | Mock KYC checklist | Real banks decide their own list |
| `calendars.weekend.*`, `calendars.holidays.*` | Weekends and fixed-date holidays for BD and six host countries | Moon-dependent holidays (Eid, Puja) are not included. Add them from the official gazette |
| `checklists.*_TUITION`, `checklists.*_LIVING` and `checklist_labels` | Indicative document lists per corridor | Each university and bank has its own list |

Every one of these can be changed by an admin in the **Rules** screen without a code change; the
change is written to the audit log with who, what and why.

## C. Scope decisions and known limits of the sandbox

- **Everything is simulated.** Providers, FX rates, KYC, SWIFT messages and settlement are
  synthetic. No bank, FX feed or identity service is contacted, and the UI says so.
- **Sandbox MFA code.** In sandbox mode a documented fixed code (`SANDBOX_MFA_CODE`) is accepted
  next to real TOTP so judges need no authenticator app. Production mode ignores it.
- **Authentication.** Login is password plus short-lived JWT with refresh rotation, not a full
  OAuth 2.0 authorization-code-with-PKCE flow against an external identity provider. This is a
  deliberate simplification for a self-contained sandbox; the token claims and lifetimes follow
  blueprint 12.2.
- **TLS and mTLS.** The compose stack serves plain HTTP on `localhost:8080`. The nginx config sends
  HSTS and the other headers, but TLS termination is expected from the real deployment. mTLS is not
  used because there is only one backend service.
- **Audit log strength.** Tamper-evident, not tamper-proof. The head hash can be published outside
  the database for extra strength; no external publication is automated.
- **Database role separation.** SQLite has no roles. Append-only behaviour on `audit_events` is
  enforced with triggers that block `UPDATE` and `DELETE`. A Postgres deployment should also revoke
  those privileges from the application role.
- **CAPTCHA** (optional in blueprint 12.1) is not implemented; rate limiting is.
- **Calendars** list fixed-date holidays only.
- **Real LLM.** The assistant runs in template mode without a key. The Anthropic and
  OpenAI-compatible clients are implemented and unit-tested against fakes, but have not been
  exercised against a live model endpoint in this sandbox. Pin `LLM_MODEL` and test once with your
  own key before the demo if you intend to show model mode.
- **Docker.** `docker compose up --build` is written and its parts were validated one by one (the
  API entrypoint, the built UI served with the repository's exact security headers, the compose
  file syntax) but the team should run it once from a clean clone on a machine with Docker before
  submission, because Docker was not available where this was built.

## D. Things only a person can supply

- The registration form and passport bio pages (never put these in the repository).
- The demo video (3 to 5 minutes, English).
- The final deck from the outline in `submission/DECK_OUTLINE.md`.
- The submission email to the organisers (see blueprint 1.4). Check the address on the official
  site first.
