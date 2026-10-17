# Security testing: attacks, tracking and data leakage

Run on 15 October 2026 against the sandbox with the tools in [`scripts/security/`](../scripts/security/).
`PASS` means the attack was **defended**. This is evidence, not a guarantee: no test can prove that
no flaw exists, and an independent penetration test has not been done.

## What was tested

| Area | How | Result |
|------|-----|--------|
| **Everything the suites cover** | `pytest` (backend), `vitest` and Playwright (web UI), `ruff`, `tsc`, ESLint, production build | All pass |
| **Known vulnerable dependencies** | `pip-audit` on the pinned backend lock; `npm audit` on the web UI (production) and on `contracts/` | 0 vulnerabilities in all three |
| **Anonymous access** | Every one of the 70 routes from the API's own OpenAPI document called with no token | All refused; no server error |
| **Token forgery** | `alg=none`, HS256 signed with the public key (algorithm confusion), ES256 with an attacker's key, cut and flipped signatures, expired, refresh token used as access token, empty and garbage bearers, token in the URL | All refused (401) |
| **One family reading another's data** | A second, unrelated household (parent and student) against payments, quotes, trackers, compliance reports, instruction previews, escrows, bank transfers and statements, recipients, documents, audit events and every list | All 403 or 404; nothing of household 1 appears anywhere in household 2's responses |
| **One family changing another's data** | Rename, cancel, request approval, abandon, confirm, delete, with and without borrowed MFA proofs | All refused; nothing changed |
| **Borrowed secrets** | An MFA proof minted for household 1 used by household 2; minting a proof for someone else's escrow; reusing another family's Idempotency-Key | Refused; the key never replays another family's response |
| **Privilege escalation** | Parent and student calling reviewer-only endpoints (rule changes, KYC override, chain anchor, freeze, sandbox clock, provider events, audit verify); the AI account signing in | All refused |
| **Injection** | Seven SQL-injection strings in query strings and JSON bodies on every text field; XSS markup; template strings | No server error, no database error or path in any response, nothing dropped |
| **Hostile input** | 3 MB body, 200,000-deep JSON, invalid UTF-8, NUL bytes, malformed JSON, mass assignment (`owner_id`, `role`, `status`), path traversal, 5,000-character ids | Clean 4xx every time |
| **Protocol abuse** | `TRACE`, CORS preflights from an evil origin, forged and missing webhook signatures, hostile `X-Request-ID` | Refused or neutralised |
| **Brute force** | Login and MFA guessing, `X-Forwarded-For` spoofing, lockout, per-user write limits, user enumeration by answer and by timing | See "Found and fixed" |
| **Data leakage (responses)** | Every response (about 260) scanned for password hashes, MFA secrets, the encrypted-account field, private keys, full IBANs, token hashes, database paths | None |
| **Data leakage (logs, files, audit)** | The server log, the database file at byte level and every audit event scanned for e-mails, passwords, tokens, MFA codes, IBANs, names and attack payloads | None. A user's IBAN is stored encrypted; only the synthetic bank-network account numbers are plain text |
| **Git** | Current tree and all 34 commits searched for keys, tokens and sensitive files; commit identities | None; only GitHub no-reply addresses |
| **Server-side egress** | A packet capture of the real backend container while the 14-step demo ran with the trained reader on, then 130 s idle | No packet to a public address (after fixing ONNX Runtime's telemetry, see "Found and fixed") |
| **Tracking and third parties** | Real Chrome through every screen as parent and reviewer, recording all 120 requests, cookies, storage, referrers and global variables | Every request went to the app's own origin. No cookie, no `Referer` header, no analytics, no CDN, no remote font |
| **Stored and reflected XSS** | Markup planted in recipient names, document names and rule reasons; hostile URLs | Shown as literal text on every screen; nothing ran |
| **CSP and framing** | Injected inline script and style, a script from another origin, a request to another origin, an iframe of the app | All blocked by the production CSP |
| **Shipped assets** | Every downloaded JavaScript and CSS file | No source maps, no keys, no tokens, no passwords |
| **Response headers** | CSP, HSTS, nosniff, frame options, referrer policy, permissions policy, `Cache-Control: no-store` on every response; no cookies; no server banner | Present everywhere |

## Found and fixed during this run

1. **E-mail addresses could be discovered.** After repeated failures a real account answered 429
   while an unknown address kept answering 401, so an attacker could tell which addresses have
   accounts. `FailedLoginTracker` now counts failures per address whether or not the account
   exists; both lock after the same number of failures with an identical answer. Tests:
   `test_real_and_made_up_addresses_lock_the_same_way...` and two more in `test_api_auth.py`.
2. **The server announced itself** (`Server: uvicorn`). The container now starts uvicorn with
   `--no-server-header` (a test checks the entrypoint).
4. **A dependency phoned home.** After the trained reader was added, a packet capture of the real
   backend container showed ONNX Runtime 1.31 looking up `mobile.events.data.microsoft.com` and
   opening an HTTPS connection about ten seconds after first use: its telemetry is on by default on
   Linux. It is now switched off in the code (before the library is imported, and through its API)
   and in the image (`ENV ORT_DISABLE_TELEMETRY=1`), both checked by tests, and the capture was
   repeated: with the demo and 130 seconds of idle, no packet left for a public address and no DNS
   lookup mentioned Microsoft. Evidence: `submission/evidence/docker_telemetry_capture.txt`.
3. **A real accessibility bug in the MFA dialog** (`role="dialog"` on a `<form>`), found when the
   dialog was first checked while open. Fixed.

New regression tests so none of it can quietly come back: `test_security_households.py` (a second
household cannot read, change or borrow anything of the first), the uniform-lockout tests, and the
entrypoint check.

## Residual risks (also in [SECURITY_SELF_ASSESSMENT.md](SECURITY_SELF_ASSESSMENT.md))

* **The sandbox publishes its demo password and MFA code** on purpose (R29). Never put a sandbox on
  the internet. To do so anyway, set `SHOW_DEMO_HINTS=false`, `SEED_DEMO_PASSWORD` and
  `SANDBOX_MFA_CODE`.
* **The refresh token is in `sessionStorage`** (R3). No XSS flaw was found and the CSP forbids
  injected script, but a cookie that script cannot read would be stronger.
* **The container trusts `X-Forwarded-For`** because only nginx can reach the API (R30). A test keeps
  the API port unpublished.
* **Account lockout can be used to lock out someone else's account for 15 minutes.** That is the
  usual trade-off against guessing.
* **The Next.js dev server** is for development only (R31).
* **The CSP lists hashed inline scripts and four libraries are patched at install time** (R42).
* **SQLite triggers can be dropped by someone with file access.** The audit hash chain, the chain
  log's hash chain and the on-chain anchor are what detect that.
* **If an AI key is configured**, masked facts go to that provider. In the default template mode
  nothing leaves the machine.
* **Not done:** an external penetration test, a dynamic scanner such as OWASP ZAP, fuzzing of the
  AI path with a real model, and the attack probe against the Docker stack (the real-Chrome audit
  passed 40 of 40 against the real containers, and the smoke script and demo passed on them, also
  with the hardened overlay; see [DOCKER.md](DOCKER.md)).

## Repeat it

See [`scripts/security/README.md`](../scripts/security/README.md). The whole kit takes about ten
minutes, most of it waiting out rate-limit windows.
