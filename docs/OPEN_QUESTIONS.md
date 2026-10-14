# Open questions and things not done

Written 14 October 2026. Nothing here is hidden: if it is not verified or not built, it is listed.
Rule of the project: when a rule or number is uncertain it goes into `config/rules.yaml` with
`verified: false` and appears here. The app shows a yellow **Not verified** badge on each of them
and says "Indicative. Confirm with your AD bank."

## A. Competition facts (checked against the official rules on 14 Oct 2026)

Source: "PBCSF Appendix 2: Problem Description and Competition Rules for International Track" and
the CMU Thailand announcement. Re-check https://fintechathon.g-ican.com/#/en once before sending.

| # | Question | Answer from the rules | Status |
|---|----------|-----------------------|--------|
| 1 | Deadline | 20 Oct 2026, 23:59 Beijing (21:59 Dhaka). Registration and submission share it. Updates allowed until then, the latest version counts | **Confirmed** |
| 2 | Deliverables | Six: technical documentation, deck (10 minutes), demo video (optional, 5 minutes), source code with README and test cases and a GitHub link, security self-assessment, execution evidence (sandbox logs and demo video for non-on-chain topics) | **Confirmed**; all prepared in `docs/` and `submission/` except the deck file, the video and the GitHub repository |
| 3 | Scoring | Task completion 40%, security and compliance 30%, innovation and interaction 30%; bonus of 0 to 5 points only for the on-chain topic | **Confirmed** |
| 4 | Mandatory API, dataset or test environment | None stated. The evidence requirement refers to the team's own simulated account or sandbox | **Confirmed: none** |
| 5 | Team rules | 2 to 5 full-time students at institutions outside Mainland China, Hong Kong, Macao and Taiwan; at least 60% non-Chinese nationals; one team per person; the organiser assigns the track | **Confirmed. A one-person entry is not allowed** |
| 6 | Demo video required? | Item 03 says optional, but item 06 asks for sandbox operation logs **and** a demo video | **Record it** |
| 7 | Finals | At least one member of each finalist team must attend in person in Shenzhen, otherwise awards are forfeited | **Confirmed** |
| 8 | Originality | Independent work, no plagiarism; third-party and open-source parts must be licensed; IP stays with the contestants, hosts may use entries for non-commercial promotion | **Confirmed**; see `docs/THIRD_PARTY.md` |
| 9 | Exact subject line of the registration e-mail | Not stated in the rules or the announcement | **Open**: use the format printed on the registration form |
| 10 | How the 60% rule is counted (headcount or otherwise) | Not stated | **Open**: assume headcount |

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
- **Agent tasks are rule-based.** Reading "I need to pay GBP 10,000 by 28 October" uses patterns, not language
  understanding. Unusual phrasing falls back to a question that asks for the amount and gives an example.
  Only major corridor currencies are read (not "dollars" without a country), and dates are read day first.
- **Real LLM.** The assistant runs in template mode without a key. The Anthropic and
  OpenAI-compatible clients are implemented and unit-tested against fakes, but have not been
  exercised against a live model endpoint in this sandbox. Pin `LLM_MODEL`, then run
  `python -m app.scripts.check_ai` (from `backend/`) with your own key before the demo if you
  intend to show model mode. It prints OK or FAIL with the reason.
- **Bank network.** The banks, BIC-style codes (`EXMP...`), account numbers, rails (instant, next
  batch, high value), fees, limits, delays and the correspondent route in `config/bank_network.yaml`
  are **invented**. They copy the shape of real payment systems and nothing more; no real scheme's
  rules, cut-off times or limits were checked, so none is marked verified. International transfers
  run one way (Bangladesh bank, BDT, through one correspondent to a foreign account in its own
  currency); inbound and foreign-to-foreign are refused. A failed transfer is unwound exactly, with no
  return fee. The network is a separate simulation that reuses the fee engine's pricing; a
  StudyRoute payment is still settled by the simulated provider, and linking the two is a next step.
  See `docs/BANK_NETWORK.md`.
- **Docker.** `docker compose up --build` has **not been run** on the development machine, which has
  no Docker. Its parts were checked one by one: the API entrypoint from a copy laid out like the
  image, the UI built from a clean copy that honours `frontend/.dockerignore`, and the repository's
  own `nginx.conf` in a real nginx 1.28 in front of the API (`scripts/docker_smoke.py` passes and a
  headless Chrome walks the parent journey under the strict CSP). That run found and fixed one
  defect: the proxy added its own security headers to API responses, so each was sent twice.
  `docker-compose.hardened.yml` (read-only filesystem, dropped capabilities) is untested. The CI
  `docker` job builds and starts the real stack once the repository is pushed. Run
  `docker compose up --build` from a clean clone before submitting; see `docs/DOCKER.md`.

## D. Things only a person can supply

- A team of **at least two** eligible students (see section A, row 5).
- The registration form and passport bio pages (never put these in the repository).
- The GitHub repository and its link (deliverable 04).
- The demo video (under 5 minutes, English; script in `submission/VIDEO_SCRIPT.md`).
- The final deck, 10 minutes at most, from `submission/DECK_OUTLINE.md`.
- The registration and submission e-mails (drafts in `submission/EMAIL_TEMPLATES.md`).
