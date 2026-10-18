# Security testing: attacks, tracking and data leakage

Run on 15 October 2026 against the sandbox with the tools in [`scripts/security/`](../scripts/security/).
`PASS` means the attack was **defended**. This is evidence, not a guarantee: no test can prove that
no flaw exists, and an independent penetration test has not been done.

Re-run on 17 October 2026 after the cloud-assistant and cookie-session branch was merged: the
attack probe defended **122 of 122** (17 of them new, on the browser sessions) and the real-Chrome
audit under the production CSP passed **42 of 42**.

## Re-run of 18 October 2026 (after the AI risk score, the bank review desk and the trained explainer)

Same tools, throwaway lab databases (never the dev data), current code. The raw output of each tool is
in [`submission/evidence/security_2026-10-18/`](../submission/evidence/security_2026-10-18/).

| Area | Tool | Result |
|------|------|--------|
| Every route, forgery, cross-household access, injection, hostile input, CORS, webhooks, browser sessions, leakage, headers, **and the new bank review desk** | `attack_probe.py` | **146 of 146** defended (24 new: section 4b) |
| Login and MFA brute force, lockout, rate limits, user enumeration | `brute_probe.py` | **8 of 8** defended |
| Canary secrets in the database file, logs, audit log and responses | `leak_scan.py` | **All clear** (50 checks) |
| Man in the middle | `mitm_probe.py` | **14 defended, 0 failed** (plus 4 informational) |
| The assistant as an attack target | `assistant_probe.py` | **42 of 42** defended |
| Real Chrome under the production CSP, **now also the Bank review screen and a payment page with markup planted in the recipient name, the reviewer's note and the parent's reply** | `browser_audit.mjs` | **48 of 48** |

What the 24 new bank-review checks (section 4b of `attack_probe.py`) show:

- The reviewer's queue is closed to parents, students and another household (403).
- Another household cannot read, answer or remind a review (no data returned).
- A parent, a student or another parent cannot clear a review, **even holding an MFA proof of their own**.
- The reviewer's yes is refused without an MFA proof, with a proof minted for a different payment, with a
  proof minted for a different action, without an Idempotency-Key, with an unknown decision value, and with
  extra fields (mass assignment).
- While a review is open the parent cannot approve the payment, even with a fresh proof
  (`BANK_REVIEW_PENDING`), and none of the refused attempts changed the review.
- Controls: the reviewer with a fresh proof can clear it, and the same proof cannot be used a second time.

**A finding from this pass, in the probe and not in the app.** The first run of `mitm_probe.py` showed
5 failures. The lab household had made many payments, so the AI risk score sent the probe's payment to
the bank's reviewer, and the approval answered 409 `BANK_REVIEW_PENDING` instead of the 403 the probe
expected for a missing MFA proof. That is the review gate working, but it also meant the probe was no
longer testing the approval step. The probe now clears the review the way a reviewer would (a person
with a fresh `review_payment` proof) before it attacks the approval, and then passes 14 of 14. The order
of the two checks (review gate first, MFA second) is by design and both must pass for an approval.

**Still not covered by this pass:** a real language model; the TLS probe and the Docker packet capture
(not re-run, no change to either); an independent penetration test. These probes were written by the
same team that wrote the app, so they find what the team thought to try.

## Full pass of 17 October 2026 (after merging the cloud assistant and cookie sessions)

Everything below ran against the final code in throwaway lab databases (never the dev data).

| Area | Tool | Result |
|------|------|--------|
| Every route, forgery, cross-household access, injection, hostile input, CORS, webhooks, browser (cookie) sessions, leakage, headers | `attack_probe.py` | **122 of 122** defended |
| Login and MFA brute force, lockout, rate limits, `X-Forwarded-For` spoofing, user enumeration by answer and by timing | `brute_probe.py` | **8 of 8** defended |
| Data theft at rest and in logs: 14 planted canaries searched for in the database file and its log, the server log, the audit log and the responses | `leak_scan.py` | **All clear** (50 checks). Found and fixed: document text was plain in the database (see below) |
| Man in the middle: a changed approval hash, a redirected approval, a stripped or swapped MFA proof, a stolen token, replayed approvals, forged, stale, cross-provider and replayed webhooks | `mitm_probe.py` | **14 defended, 0 failed** (plus 4 informational) |
| TLS: versions, HSTS, `Secure` cookie, plain HTTP on the TLS port | `tls_probe.py` | **8 of 8** (TLS 1.0 and 1.1 refused, 1.2 and 1.3 accepted) |
| The assistant as an attack target: 20 hostile prompts as parent and as student | `assistant_probe.py` | **42 of 42** defended |
| Real Chrome through every screen under the production CSP (XSS in stored data, injected scripts and styles, framing, third parties, cookies, storage, source maps) | `browser_audit.mjs`, `csp-interact.mjs` | **42 of 42**, 0 problems |
| Network egress of the API process during the full 14-step demo (265 samples over 150 s) | connection sampling | **No outbound connection** to a non-loopback address |
| Secrets in the whole git history (71 commits, every branch) and sensitive file names | pattern scan | **None** (one fake JWT in a masking test) |
| Known vulnerable dependencies | `pip-audit`, `npm audit`, `npm audit` (contracts) | **0** in the Python lock, the web production tree and contracts. 9 "high" advisories in dev-only tooling (see below) |
| Bandit-style code rules (`ruff --select S`) | ruff | **No findings** |
| The trained reader against attacks | `ml/evaluate.py` | Unchanged: attacks blocked 85 to 93% depending on the set (docs/AI_EVALUATION.md) |
| All suites | pytest, vitest, Playwright | See `docs/TEST_CASES.md` |

**What a man in the middle can still do on plain HTTP** (reported by `mitm_probe.py` as informational, risk R4): read the
sign-in password and every bearer token, read the family's payments with a captured token until it expires (15 minutes), and cancel a
pending draft. They cannot approve, allowlist or de-list anything without a fresh MFA proof, cannot change what the person approves
(the summary hash and the proof are bound to it), and cannot replay a recorded approval. TLS in front of the stack closes the reading.

**What this pass did not cover:** a real language model (none is connected, so prompt-injection results are for the shipped
assistant only); a packet capture of the Docker container (no Docker here; the earlier capture is in `submission/evidence/`);
nginx's own TLS configuration (the probe used the application's TLS); an independent penetration test.

## What was tested

| Area | How | Result |
|------|-----|--------|
| **Everything the suites cover** | `pytest` (backend), `vitest` and Playwright (web UI), `ruff`, `tsc`, ESLint, production build | All pass |
| **Known vulnerable dependencies** | `pip-audit` on the pinned backend lock; `npm audit` on the web UI (production) and on `contracts/` | 0 vulnerabilities in all three |
| **Anonymous access** | Every route from the API's own OpenAPI document (the student budget and arrival guide included) called with no token | All refused; no server error |
| **Token forgery** | `alg=none`, HS256 signed with the public key (algorithm confusion), ES256 with an attacker's key, cut and flipped signatures, expired, refresh token used as access token, empty and garbage bearers, token in the URL | All refused (401) |
| **One family reading another's data** | A second, unrelated household (parent and student) against payments, quotes, trackers, compliance reports, instruction previews, escrows, bank transfers and statements, recipients, documents, audit events and every list | All 403 or 404; nothing of household 1 appears anywhere in household 2's responses |
| **One family changing another's data** | Rename, cancel, request approval, abandon, confirm, delete, with and without borrowed MFA proofs | All refused; nothing changed |
| **Borrowed secrets** | An MFA proof minted for household 1 used by household 2; minting a proof for someone else's escrow; reusing another family's Idempotency-Key | Refused; the key never replays another family's response |
| **Privilege escalation** | Parent and student calling reviewer-only endpoints (rule changes, KYC override, chain anchor, freeze, sandbox clock, provider events, audit verify); the AI account signing in | All refused |
| **Injection** | Seven SQL-injection strings in query strings and JSON bodies on every text field; XSS markup; template strings | No server error, no database error or path in any response, nothing dropped |
| **Hostile input** | 3 MB body, 200,000-deep JSON, invalid UTF-8, NUL bytes, malformed JSON, mass assignment (`owner_id`, `role`, `status`), path traversal, 5,000-character ids | Clean 4xx every time |
| **Protocol abuse** | `TRACE`, CORS preflights from an evil origin, forged and missing webhook signatures, hostile `X-Request-ID` | Refused or neutralised |
| **Browser (cookie) sessions** | Sign-in with no, foreign, null or cross-site Origin and without the browser header; a wrong password; a stolen cookie replayed from a foreign Origin; an access token lifted from the page without its cookie; the cookie alone as API authority; a made-up cookie; logout, then replay of the old cookie and token (probe checks 6.10 to 6.21) | All refused; no cookie set on a refusal; the cookie is HttpOnly, SameSite=Strict and limited to the API path |
| **Brute force** | Login and MFA guessing, `X-Forwarded-For` spoofing, lockout, per-user write limits, user enumeration by answer and by timing | See "Found and fixed" |
| **Data leakage (responses)** | Every response (about 260) scanned for password hashes, MFA secrets, the encrypted-account field, private keys, full IBANs, token hashes, database paths | None |
| **Data leakage (logs, files, audit)** | The server log, the database file at byte level and every audit event scanned for e-mails, passwords, tokens, MFA codes, IBANs, names and attack payloads | None. A user's IBAN is stored encrypted; only the synthetic bank-network account numbers are plain text |
| **Git** | Current tree and all 34 commits searched for keys, tokens and sensitive files; commit identities | None; only GitHub no-reply addresses |
| **Server-side egress** | A packet capture of the real backend container while the 14-step demo ran with the trained reader on, then 130 s idle | No packet to a public address (after fixing ONNX Runtime's telemetry, see "Found and fixed") |
| **Tracking and third parties** | Real Chrome through every screen as parent and reviewer, recording every request (about 1,500), cookies, storage, referrers and global variables | Every request went to the app's own origin. The only cookie is the HttpOnly, SameSite=Strict session cookie, which script cannot read; no `Referer` header, no token in storage, no analytics, no CDN, no remote font |
| **Stored and reflected XSS** | Markup planted in recipient names, document names and rule reasons; hostile URLs | Shown as literal text on every screen; nothing ran |
| **CSP and framing** | Injected inline script and style, a script from another origin, a request to another origin, an iframe of the app | All blocked by the production CSP |
| **Shipped assets** | Every downloaded JavaScript and CSS file | No source maps, no keys, no tokens, no passwords |
| **Response headers** | CSP, HSTS, nosniff, frame options, referrer policy, permissions policy, `Cache-Control: no-store` on every response; a cookie only from the browser sign-in routes; no server banner | Present everywhere |

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

5. **Uploaded document text sat in the database in plain text** (found by `leak_scan.py` on 17 October: a passport number
   pasted into a document could be read from a copy of the database file, while IBANs were already encrypted). The text is now
   AES-256-GCM encrypted, bound to its own row so a ciphertext cannot be moved to another document; older plain rows are still read.
   Tests: `test_documents_at_rest.py` (6). File names and recipient display names stay plain on purpose: they are listed on screen.
6. **9 "high" npm advisories in development tools** (the `shadcn` command-line tool and `eslint-config-next`, through `braces`,
   `micromatch` and `fast-glob`: a pattern-matching denial of service). None is in the production tree (`npm audit --omit=dev` finds 0),
   which is what CI checks. Not fixed: the fix is a major upgrade of a build-time tool. Recorded as R50.

The probes above are run by hand against a lab. Their key checks are also in the normal test suites, so a regression fails `pytest` or
`npm test` (and CI) without anyone remembering to run a script:

| Test file | What it keeps true |
|-----------|--------------------|
| `backend/tests/test_security_leaks.py` (28) | 12 planted secrets (password, a wrong password, tokens, the session cookie, an MFA proof, a full IBAN, chat e-mail, phone and passport, document text) are not in the database file, the audit log or the logs; responses never repeat a typed password or a full IBAN; a positive control proves the database and the logs are really being read |
| `backend/tests/test_security_thief.py` (4) | a captured bearer token alone cannot approve, allowlist or de-list; a payment to a recipient the thief added cannot be put up for approval; replaying a recorded approval makes one approval |
| `backend/tests/test_documents_at_rest.py` (6) | document text is encrypted, bound to its row, and older plain rows still read |
| `backend/tests/test_ai_hostile_prompts.py` (2) | 20 hostile prompts as parent and as student: no secret, no key, no instructions repeated, no forbidden action proposed, no payment changed |
| `web/components/guide/guide-slider.test.tsx` (5), `web/components/compare/cost-bars.test.tsx` (4), `web/components/layout/theme-menu.test.tsx` (1), `web/tests/motion-css.test.ts` (5), `web/components/app/copy-button.test.tsx` (2) | the budget slider and the typed amount drive each other and the request; cost bars are proportional, coloured by meaning and decorative only; the theme fade starts and stops; the stylesheet has every keyframe, removes motion for people who ask, and loads nothing from another site |
| `web/e2e/smoke.spec.ts` (2 new) | in a real browser the slider changes the cities that fit, and with reduced motion entrance animations have no duration or delay |

New regression tests so none of it can quietly come back: `test_security_households.py` (a second
household cannot read, change or borrow anything of the first), the uniform-lockout tests, and the
entrypoint check.

## Residual risks (also in [SECURITY_SELF_ASSESSMENT.md](SECURITY_SELF_ASSESSMENT.md))

* **The sandbox publishes its demo password and MFA code** on purpose (R29). Never put a sandbox on
  the internet. To do so anyway, set `SHOW_DEMO_HINTS=false`, `SEED_DEMO_PASSWORD` and
  `SANDBOX_MFA_CODE`.
* **Browser sessions use an HttpOnly cookie** (R3 updated). Tokens are not stored in
  sessionStorage/localStorage. XSS could still act as the user; HttpOnly is not an XSS cure.
  CSRF rejection, absolute expiry, logout revocation and concurrent tab restore are tested in
  `test_browser_session.py`. Legacy bearer API refresh rotation is retained.
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
