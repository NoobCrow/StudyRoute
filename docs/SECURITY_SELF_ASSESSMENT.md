# Security self-assessment report

International Track deliverable 05: **permission-tier implementation and known-risk list.**
StudyRoute is a sandbox with synthetic data; this report says what is enforced, where, how it is
tested, and what is *not* solved. The control-by-control threat matrix is in
[SECURITY.md](SECURITY.md); the design is in [TECHNICAL_DOCUMENTATION.md](TECHNICAL_DOCUMENTATION.md).

## 1. Permission tiers

Authorisation is enforced in the **domain layer** (`backend/app/domain/rbac.py`), not only in the
UI or the route. A call needs both the role's permission **and** the matching scope in the access
token, so a narrowed token cannot do more than it was issued for. Objects belong to a household:
a request for another household's object gets `404`, the same answer as for a missing one.

### 1.1 Tiers

| Tier | Who | What | How it is enforced |
|------|-----|------|--------------------|
| **0. Public** | Anyone | Sign in, refresh, sign out, `GET /health`, `GET /sandbox` (sandbox only) | Rate limit by IP. `/sandbox` returns 404 in production |
| **0b. Provider** | A provider adapter | `POST /webhooks/provider` | HMAC signature with timestamp window and event-id de-duplication, not a bearer token |
| **1. Read** | Parent, student, admin, AI (read scopes) | Quotes, payments, recipients, rules, checklist, planner | Role permission plus token scope plus household ownership |
| **2. Prepare** | Parent, student (limited), AI (draft and request only) | Create quotes, drafts, recipients, documents; request approval | Role permission plus scope. A student cannot draft; the AI can only propose |
| **3. Decide (step-up)** | **Human parent only** | Approve a payment, allowlist or de-list a recipient | Everything in tier 2, plus a **fresh MFA proof** (5 minutes, single use, bound to the user, the action and the object), plus the approval summary hash |
| **4. Administer** | Admin (reviewer) | Change rules (audited), verify the audit chain, review KYC, reject a payment, drive the simulated provider (sandbox only) | Admin-only permission. An admin **cannot** approve, draft or quote |
| **Never** | The AI service account | Approve, submit, cancel, reject, allowlist, change limits, edit config, verify the audit log | Not in its permission set or token scopes; the approve path also returns `AI_CANNOT_APPROVE` and writes an audit event |

### 1.2 Permission matrix (generated from the code)

`yes` means the role holds the permission. A test (`test_security_self_assessment.py`) fails if this
table and `ROLE_PERMISSIONS` ever differ.

| Permission | Parent | Student | Admin | AI agent |
|------------|--------|---------|-------|----------|
| `quotes:create` | yes | yes | - | yes |
| `quotes:read` | yes | yes | yes | yes |
| `payments:read` | yes | yes | yes | yes |
| `payments:draft` | yes | - | - | yes |
| `payments:request_approval` | yes | - | - | yes |
| `payments:approve` | yes | - | - | - |
| `payments:cancel` | yes | - | - | - |
| `payments:reject` | yes | - | yes | - |
| `recipients:create` | yes | yes | - | - |
| `recipients:read` | yes | yes | yes | yes |
| `recipients:allowlist` | yes | - | - | - |
| `config:read` | yes | yes | yes | yes |
| `config:write` | - | - | yes | - |
| `audit:read` | yes | - | yes | - |
| `audit:verify` | - | - | yes | - |
| `kyc:read` | yes | yes | yes | yes |
| `kyc:submit` | yes | yes | - | - |
| `kyc:review` | - | - | yes | - |
| `planner:read` | yes | yes | - | yes |
| `checklist:read` | yes | yes | yes | yes |
| `chat:use` | yes | yes | - | - |
| `mfa:issue` | yes | - | - | - |
| `documents:read` | yes | yes | - | yes |
| `documents:write` | yes | yes | - | - |
| `data:reset` | yes | - | - | - |
| `sandbox:control` | - | - | yes | - |

### 1.3 Guards that apply on top of permissions

| Action | Extra guards (all must pass) |
|--------|------------------------------|
| Request approval | Quote not expired, KYC verified, recipient allowlisted, mock sanctions clear, per-transaction and daily caps |
| Approve | The same guards again, fresh MFA proof for this payment, `confirm_summary_hash` equals the frozen summary, `Idempotency-Key`, optimistic lock |
| Allowlist a recipient | Fresh MFA proof for this recipient; renaming a recipient resets its allowlist |
| Webhook | Valid HMAC, timestamp within 300 seconds, unseen event id, matching provider and UETR |
| Change a rule | Admin permission, a reason, audit event with before and after hashes |

Each row has a test; see `backend/tests/test_api_payment_guards.py`, `test_api_roles.py`,
`test_api_ai_rbac.py`, `test_api_webhooks.py` and `test_rbac.py`.

## 2. Known-risk list

Severity is the team's own judgement for a **sandbox that may one day be taken towards
production**. "Accepted" means we chose not to fix it in this submission and say so openly.

| ID | Risk | Severity | Mitigation in place | Residual status |
|----|------|----------|---------------------|-----------------|
| R1 | **Sandbox MFA code is a fixed documented value**, and demo credentials are shown on the sign-in page | Medium (sandbox only) | Both exist only in sandbox mode and `SHOW_DEMO_HINTS` can switch the hints off; production forces the fixed code to `None` and refuses to start without real secrets | Accepted for the demo. Real TOTP works in every mode |
| R2 | **No external identity provider or PKCE flow**: password plus our own tokens | Medium | Argon2id, ES256 tokens (15 minutes), rotation with reuse detection, lockout, MFA step-up | Accepted; documented as a simplification |
| R3 | **Refresh token is kept in `sessionStorage`**, readable by script if XSS ever occurs | Medium | CSP forbids inline script and style; React escapes output; T23 test; bearer tokens never go in cookies, so there is no CSRF surface | Accepted. An HttpOnly cookie with CSRF tokens would be the next step |
| R4 | **Plain HTTP in the compose stack** | Medium for production, none for the sandbox | HSTS and other headers are sent; TLS termination is expected in front of nginx | Open until deployed behind TLS |
| R5 | **The API trusts `X-Forwarded-For`** (`--forwarded-allow-ips="*"`) so per-IP rate limits see the real client | Medium if the API port were exposed | Compose publishes only nginx, which overwrites the header | Accepted; do not publish the API port |
| R6 | **Rate-limit counters live in process memory** | Low | Correct for one process; limits would multiply behind several workers | Open: use a shared store before scaling out |
| R7 | **Audit log is tamper-evident, not tamper-proof.** Someone with database file access can drop the triggers (the demo script does exactly this) | Medium | Hash chain plus Verify detects any edit; the head hash can be compared with an externally published value to detect tail truncation | Open: publishing the head hash is manual |
| R8 | **SQLite has no database roles**, so "application cannot update audit rows" is enforced by triggers only | Low | Triggers block `UPDATE` and `DELETE`; test `test_application_role_cannot_update_or_delete_audit_rows` | Open: on Postgres, also revoke the privileges |
| R9 | **Prompt-injection filter is heuristic.** A new phrasing might slip past the policy patterns | Medium | Defence in depth: no tool can approve, submit, cancel or change limits; the number guard blocks invented figures; the model sees masked data only; a person must approve with MFA | Accepted: the worst outcome is a harmless reply, not an action |
| R10 | **The number guard checks numbers, not wording.** A model could state a non-numeric claim such as "this is allowed" | Medium | The system prompt forbids it; questions about legality get a fixed "I cannot say whether something is legal" answer and the "Indicative. Confirm with your AD bank." line; template mode needs no model | Accepted; human reviews the engine's approval summary |
| R11 | **Regulatory values are unverified** (living-expense limit, circulars, cut-off, calendars, checklists) | High if presented as real | Every one is in config with `verified: false`, a yellow **Not verified** badge and an indicative disclaimer; listed in `docs/OPEN_QUESTIONS.md` | Open until checked against official sources |
| R12 | **Sanctions screening is a test token**, not a real list | Low (sandbox) | Labelled "mock" everywhere; blocked names are audited | Accepted |
| R13 | **Sandbox secrets are generated under `data/`** (gitignored) | Low | Never committed (scanner enforces it); production needs environment secrets | Accepted |
| R14 | **Dependencies are pinned but not scanned automatically** for known vulnerabilities | Medium | Backend versions pinned in `requirements.txt`; npm lock file; CI runs tests, lint and a secret scan | Open: add a dependency audit to CI |
| R15 | **The live-model path is tested with fakes only** | Low | `check_ai` command verifies a configured model end to end before use; fallback to template answers if the model fails or invents a number | Open until a key is configured |
| R16 | **No CAPTCHA** on sign-in | Low | Rate limit by IP and account lockout | Accepted (optional in the design) |
| R17 | **Simulated systems could be mistaken for real ones** | Medium | Banner on every screen, `X-Sandbox: true` on every API response, "simulated" on every provider-related view, no claim of a live bank or FX feed | Mitigated |

## 3. What we tested and how to repeat it

```bash
cd backend && pytest -q               # blueprint T01-T24 plus AI, sandbox and demo tests
python -m app.scripts.demo_flow       # ten-step demo against a running API
python -m app.scripts.tamper_audit    # edit one audit row, then Verify must FAIL at that sequence
python scripts/scan_repo.py           # no secrets, real e-mails, passport-like numbers or TODOs
```

Operation logs from a real run are in `submission/evidence/`.
