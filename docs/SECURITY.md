# StudyRoute security design

StudyRoute is a **sandbox**: no real money moves, all data is synthetic, and every screen says so.
This page maps each threat from blueprint section 12.1 to the control that stops it and to the
test or demo step that proves it. Test names refer to `backend/tests/`. Demo steps refer to
`python -m app.scripts.demo_flow` (it prints OK or FAIL for each) and to the screens in the UI.

> The engine calculates, the AI explains, the human approves, and every step is logged.

## Threat and control matrix

| Threat | Control | Proof |
|--------|---------|-------|
| **Account takeover** | Argon2id passwords, ES256 access tokens that live 15 minutes, refresh tokens that rotate and revoke the whole family on reuse, lockout after repeated failures, a fresh MFA proof (5 minutes, single use, bound to the user, the action and the object) for approval and allowlisting | `test_passwords_and_mfa_secrets_are_stored_hashed_and_encrypted`, `test_repeated_failures_lock_the_account_for_a_while`, `test_refresh_tokens_rotate_and_reuse_revokes_the_whole_family`, `test_access_tokens_expire_after_fifteen_minutes`, T08 in `test_api_payment_guards.py`. Demo: approve without MFA gives 403 `MFA_REQUIRED` (step 8) |
| **Double payment** | Idempotency-Key on every payment write (stored for 24 hours in the same transaction), optimistic locking on `payments.version`, unique constraints | T04 and T05 in `test_api_idempotency.py`, `test_two_simultaneous_approvals_cannot_both_succeed`. Demo: replaying approve returns `Idempotent-Replay: true` and writes no second audit event (step 8, and the **Security demo** panel on a payment) |
| **Forged status update** | HMAC-SHA256 over `timestamp.raw_body`, constant-time compare, 300 second window, event-id de-duplication, one secret per provider with rotation | T12, T13 and T14 in `test_api_webhooks.py` and `test_webhook_signing.py`. Demo: forged webhook gives 401 and a `webhook.rejected` audit event (step 9) |
| **Privilege abuse** | Role-based access control checked in the domain layer, not only the UI; ownership checks return 404 for other users' objects; token scopes checked as well as roles | T10 and T11 in `test_api_roles.py`, `test_rbac.py`. Demo: the student's approve gives 403 `FORBIDDEN` (step 8) |
| **AI approves a payment** | The AI service account has no approve scope and the approve path refuses it with `AI_CANNOT_APPROVE` and an audit event. The tool allow-list has no approve, submit, cancel, limit or config tool | T09 in `test_api_ai_rbac.py`, `test_privileged_tools_are_never_available_to_the_ai`. Demo: tell the chat to approve; it is refused and `ai.blocked` is logged (step 9) |
| **Prompt injection** | Policy check on the message and on document text before anything else; all user and document text is passed as data; allow-listed tools with strict argument validation; proposals only, a human clicks every state change | `test_blueprint_red_team_prompts_are_flagged`, T19 in `test_ai_redteam.py`, `test_an_uploaded_document_that_says_send_the_money_is_treated_as_data` |
| **AI invents a number** | The engine produces every number. The number guard checks every number in a reply against the facts the reply cites; on a mismatch it retries once, then falls back to a template answer | T20 in `test_ai_llm_mode.py`, `test_ai_number_guard.py`. UI: every answer lists `facts_used` |
| **Data leakage to the LLM** | Names become numbered tokens, accounts show country and last four, passports, e-mails and phones are removed and never restored, addresses reduce to a country. The masked prompt is visible in the chat's debug view | `test_ai_masking.py`. UI: "Debug: what the model sees (masked)" under each answer |
| **Log tampering** | Append-only audit log in the same transaction as each state change, hash-chained with SHA-256, triggers that block `UPDATE` and `DELETE`, a verify endpoint, optional comparison with an externally published head hash | T16 in `test_audit.py` and `test_api_audit_config.py`, `test_application_role_cannot_update_or_delete_audit_rows`. Demo: Verify gives PASS (step 13); `python -m app.scripts.tamper_audit` then Verify gives FAIL at that sequence |
| **Injection and XSS** | Parameterised queries (SQLAlchemy), strict request schemas that reject unknown fields, React escapes all output, CSP `default-src 'self'` with no inline script or style, control characters stripped from names | T23 in `test_security.py` and the frontend test in `Recipients.test.tsx`. Demo: save `<script>` as a recipient name; it shows as text |
| **Abuse and brute force** | Per-IP and per-user rate limits (blueprint 8.7), request size limit, lockouts | T22 in `test_api_auth.py` (429 with `Retry-After`), `test_oversized_bodies_are_refused_before_they_are_read` |
| **Money moved wrongly between the simulated banks** | Every posting is a balanced double-entry journal; a journal that would overdraw an account is refused before anything changes; ledger rows are append-only; a failed transfer is unwound by reversing journals; a transfer is confirmed only by a human with an MFA proof bound to that transfer; the AI has no bank permission; every hop writes one audit event | `test_ledger.py`, `test_engine_interbank.py`, `test_api_bank.py` (MFA binding, single use, idempotency, roles, unwind, `all_ok` after every flow). Demo: step 12; the **Do the books balance?** card; a balance edited behind the ledger turns it red |
| **Stale or wrong quote** | Quotes expire after 300 seconds; approval needs the hash of the summary the human saw, so a changed amount or recipient cannot be approved by mistake | T06 in `test_api_payments.py`, `test_api_payment_guards.py`. UI: live countdown on every quote |
| **Secret leakage** | No secrets in the repository. Environment variables or generated throw-away sandbox secrets under `data/` (gitignored). Production mode refuses to start with a missing secret. Secret scan in CI | `test_production_mode_refuses_to_invent_secrets`, `test_repo_scan.py`, `scripts/scan_repo.py` run by the `secret-scan` CI job; `.env.example` has empty values only |
| **AI takes a state-changing action** | The assistant may create a quote, because the RBAC matrix allows it, and nothing more. Messages flagged by the policy check start no task. It cannot create a payment, approve, submit, cancel, allowlist or change limits; its draft is a proposal a human confirms | `test_ai_tasks.py` (`test_the_assistant_creates_a_quote_and_nothing_else`, `test_an_injection_wrapped_around_a_plan_creates_nothing`). Demo: step 4 |
| **A compliance report is edited after it was produced** | Every report carries a SHA-256 of its own canonical JSON; the screen recomputes it in the browser ('Verify this report'), so a changed copy shows 'Does not match' | `test_the_report_hash_lets_anyone_detect_a_changed_report`, `Report.test.tsx`, `canonical.test.ts` (the browser hash equals the backend hash). Demo: step 11 |
| **Sandbox mistaken for production** (design addition) | `X-Sandbox: true` on every API response and the banner on every screen while `APP_ENV=sandbox`; neither exists in production, and the sandbox endpoints (`/sandbox`, provider-event) answer 404 there | `test_api_sandbox.py` (marker on 200, 401, 404 and 422; `test_production_mode_has_no_sandbox_surface_and_no_marker`) |
| **Abuse of the simulated provider** (design addition) | Provider-event control needs the admin-only `sandbox:control` permission (never held by the AI, a parent or a student), works only on a payment in flight, acts only by scheduling the signed webhook through the normal path, and writes `sandbox.provider_event_scheduled` to the audit log | `test_only_an_admin_may_trigger_provider_events`, `test_a_payment_that_is_not_in_flight_cannot_be_triggered`, `test_rbac.py` |
| **Wrong recipient** (design addition) | The draft form never preselects a recipient when more than one exists; a recipient must be allowlisted with MFA before approval | UI test `Compare.test.tsx` ("never guesses the recipient"); recipients flow in the demo (step 7) |

## Compliance self-assessment (blueprint 12.5)

| Area | What we do | Evidence in the demo |
|------|------------|----------------------|
| Know your customer | Mock KYC gate: approval is blocked unless Verified | Step 6 (blocked), step 7 (verified). The UI disables the button and says why |
| AML and monitoring | Per-transaction and daily caps from config, mock sanctions screening (`SANCTION_TEST`), audit events | T17, T18 |
| Travel rule | Originator and beneficiary data in the MT103 preview | Payment screen, "Payment instruction preview" |
| Explainability | Every AI answer lists the engine facts it used | `facts_used` in the chat |
| Human oversight | Only a human parent approves, with a fresh MFA proof | Step 8 |
| Record keeping | Tamper-evident audit log with a Verify button | Step 13 |
| Regulatory freshness | Rules in config with `source_url`, `last_checked` and a `verified` flag; yellow **Not verified** badges | Rules screen; `docs/OPEN_QUESTIONS.md` |

## Layers

- **Browser.** Static files with a strict CSP (no inline script or style), `nosniff`,
  `Referrer-Policy: no-referrer`, `frame-ancestors 'none'`, HSTS. Tokens live in memory; only the
  rotating refresh token is kept in `sessionStorage`. `credentials: "omit"`, so cookies are never
  sent and CSRF does not apply.
- **nginx.** Serves the UI and proxies `/api` on the same origin, so no CORS is needed. It sets
  `X-Forwarded-For` from the real client address (overwriting any client value). Only nginx is
  published by `docker-compose.yml`. nginx adds the page's security headers to the UI and its
  assets only; the API sets its own, stricter ones (`default-src 'none'`), and nginx does not add
  a second copy. `scripts/docker_smoke.py` and `tests/test_docker_config.py` both check this.
  `docker-compose.hardened.yml` optionally adds a read-only filesystem and dropped capabilities.
- **API.** Security middleware (headers, body limit, request id), RFC 7807 errors that never expose
  internals, CORS limited to an exact origin list without credentials.
- **Domain.** Authorisation, the state machine and every guard (KYC, allowlist, limits, sanctions,
  quote expiry, MFA, summary hash). One audit event per state change, in the same transaction.
- **Engine.** Pure functions: money as integer minor units and `Decimal` rates, never floats.
- **Logs.** A redaction filter on every logger removes tokens, e-mails, IBANs and long digit runs
  (T24).

## Known limits

See section C of `docs/OPEN_QUESTIONS.md`. In short: the sandbox MFA code is a documented fixed
value; login is not a full OIDC/PKCE flow against an external identity provider; TLS is expected
from the real deployment; the audit log is tamper-evident rather than tamper-proof.

## Reviewing the security-critical code

Read these files line by line before relying on them: `app/domain/auth.py`, `app/api/idempotency.py`,
`app/providers/webhooks.py`, `app/audit/chain.py` and `app/audit/service.py`, `app/domain/state_machine.py`,
`app/domain/rbac.py`, `app/ai/guards.py`, `app/ai/number_guard.py`, `app/ai/masking.py`.
