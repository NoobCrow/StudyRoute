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
| 10 | How the 60% rule is counted (headcount or otherwise) | The rules say "60% non-Chinese nationals, major, or year of study", which can be read more than one way | **Open**: assume headcount of nationalities; ask the organiser (draft 3 in `submission/EMAIL_TEMPLATES.md`) |
| 11 | Which countries can enter | The official rules name only the exclusions (Mainland China, Hong Kong SAR, Macao SAR, Chinese Taipei). One secondary page (IEEE R10 chapter) was reported to say "21 APEC economies" and a different theme; the official PDF says neither | **Open**: confirm with the organiser before registering (same e-mail) |
| 12 | Visa for the Shenzhen final | Finalists are announced 31 Oct and check in on 20 Nov; invitation letters come with the announcement (blueprint) | **Open**: find out the Chinese visa lead time for the member who would travel, now |

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
| `calendars.weekend.*`, `calendars.holidays.*` | Weekends and fixed-date holidays for BD and six host countries (every other country has a weekend only, from `countries.directory`) | Moon-dependent holidays (Eid, Puja) are not included. Add them from the official gazette |
| `checklists.*_TUITION`, `checklists.*_LIVING` and `checklist_labels` | Indicative document lists per corridor | Each university and bank has its own list |
| `checklists.GENERIC_TUITION`, `checklists.GENERIC_LIVING` | The general list shown for every country without its own | Country-specific documents (like a CAS or an I-20) are only loaded for the six hand-written corridors |
| `countries.directory` | Name, currency and weekend for all 198 destination countries | Taken from Unicode CLDR (through Babel), not checked against each country's banks. No public holidays are loaded for these countries |
| `student_costs.GB`, `.US`, `.DE`, `.AU`, `.CA`, `.MY` | Monthly rent, food, transport, bills, phone and other costs for 20 student cities | Invented for the sandbox, not a survey. Replace with a university's own estimate or a published cost-of-living source before anyone relies on them |
| `arrival_guide.*`, `arrival_labels` | The first-weeks steps for each country, and the label and hint of each step | Indicative advice. Visa, work and registration rules differ by country and change; confirm with the university and the official government page |
| `countries.restricted` | Destinations the sandbox lists but will not quote (CU, IR, KP, SY) | A placeholder from public sanctions news, not legal advice. Which destinations a Bangladeshi AD bank refuses must come from Bangladesh Bank and the bank itself |

Every one of these can be changed by an admin in the **Rules** screen without a code change; the
change is written to the audit log with who, what and why.

## C. Scope decisions and known limits of the sandbox

- **Everything is simulated.** Providers, FX rates, KYC, SWIFT messages and settlement are
  synthetic. No bank, FX feed or identity service is contacted, and the UI says so.
- **No real-world calibration, no real users, no outside review.** The provider fees, spreads and
  the 20 cities' costs are invented, so "Provider B is cheapest at 1.58%" shows how the engine
  ranks, not what a real provider would charge. The engine has not been checked against a real
  published quote, no real parent or student has tried the app, and nobody outside the project
  has tested its security. The way to close the first gap is to take a few dated public quotes
  for one corridor, enter the same inputs, and publish the difference; the way to close the
  second is to time five outsiders on the same task against a spreadsheet. Neither was done.
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
- **Smart escrow and the chain.** The chain is an in-memory EVM, not a network: no peers, no
  consensus, no gas, no keys. The "tokenised deposit" is a sandbox token the bank mints against a
  simulated debit; it is not linked to the Bank network screen. The contracts target Solidity 0.8.x
  and the `paris` EVM so they should run on other EVM-compatible chains, **but this has not been
  tried**. Which party would really issue the token, hold the compliance key and run the nodes in a
  Bangladeshi AD-bank setting, and what Bangladesh Bank allows for tokenised deposits, are open and
  not answered here. See `docs/SMART_ESCROW.md`.
- **The trained reader.** A small model fine-tuned on a GPU reads what a parent types (see
  `docs/AI_AGENT.md`). Its training data is **synthetic plus public** (generated messages and a UK
  bank's questions from Banking77); no real parent's messages exist, so it has not been tested on
  real users and its confidence thresholds were tuned on generated data. The blind test set is small
  (113 messages), so its numbers are good to about plus or minus 7 points. Attack detection is an
  extra layer: on unseen wording it blocked 85% of attacks, and a few novel ones get through to a
  harmless answer. It was not red-teamed by outsiders. The model file is not signed (R33).
  A real language model through `LLM_PROVIDER` has still never been run in this project. NumPy 2
  needs a CPU with SSE4.2; without it the reader is skipped and the rules answer (tested by accident
  in a VM). The submission archive is about 30 MB because the model is in it; the source deliverable
  is the GitHub link.
- **The reinforcement-learning dialogue policy.** A small policy decides when to ask, read back or
  plan (see `docs/AI_RL.md`). It was trained against **simulated parents** whose behaviour and
  rewards are my assumptions (how often a parent mistypes or mentions another amount, that a wrong
  amount costs twice what a correct plan earns, that a question costs a twentieth of it). What a
  real parent would find annoying, and how much a wrong quote card really costs, are not known; the
  policy has never met a real person. On the simulator it keeps about 1% wrong plans while asking
  40% fewer questions than the best hand-written rule, which asks every time and has none. Whether
  that trade is right is a product decision, not a result. Under a -10 wrong-amount reward it did
  not quite match "always confirm" (a limit of DQN on rare costly events). Nobody outside the
  project has reviewed the simulator or the policy (R39 and R40).
- **Docker.** `docker compose up --build` was run for real on 15 October 2026 from the unzipped
  submission archive, with Docker Engine 29.1.3 and Compose 2.40.3 inside an Ubuntu 24.04 `amd64`
  virtual machine (Docker Desktop could not be installed on the development machine). Both images
  built and started healthy; `scripts/docker_smoke.py`, the 14-step demo and the 40-check
  real-Chrome audit under the strict CSP passed, data survived `down` and `up`, and
  `docker-compose.hardened.yml` (read-only filesystem, dropped capabilities) started and passed too.
  **Still open:** Docker Desktop on Windows or macOS, `arm64`, and the GitHub Actions `docker` job
  (it runs when the repository is pushed). See `docs/DOCKER.md`.

## D. Things only a person can supply

- A team of **at least two** eligible students (see section A, row 5). The team reported on 17 Oct
  2026 that it has registered; this repository cannot check that. Still open: the organiser's answers
  to section A rows 10 and 11 if the registration reply did not settle them, and row 12 (visa).
- Answers, in the team's own words, to the questions in `submission/QA_PREP.md` that say so (who built
  what, which tools were used).
- The registration form and passport bio pages (never put these in the repository).
- The GitHub repository and its link (deliverable 04).
- The demo video (under 5 minutes, English; script in `submission/VIDEO_SCRIPT.md`).
- The final deck, 10 minutes at most, from `submission/DECK_OUTLINE.md`.
- The registration and submission e-mails (drafts in `submission/EMAIL_TEMPLATES.md`).
