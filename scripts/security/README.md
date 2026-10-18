# Security test tooling

Black-box tests that attack a running StudyRoute the way an outsider would. They are **sandbox lab
tools**: they create hostile records in a throwaway database, so never point them at data you care
about. Results and what they found: [docs/SECURITY_TESTING.md](../../docs/SECURITY_TESTING.md).

| Script | What it does |
|--------|--------------|
| `lab_setup.py` | Seeds the demo household **and a second, unrelated household** in a throwaway database, so cross-household attacks can be tried. |
| `attack_probe.py` | About 150 attacks, including the bank review desk (who may open the queue, who may clear a review, MFA proofs for the wrong payment or action, replay of a used proof): anonymous access to every route, forged tokens (`alg=none`, algorithm confusion, wrong key, expired, refresh-as-access), one household reading or changing another's data, privilege escalation, SQL injection, XSS text, oversized and malformed bodies, CORS, webhook forgery, borrowed MFA proofs and Idempotency-Keys. Then scans every response for leaked secrets and checks the headers. |
| `brute_probe.py` | Login and MFA brute force, account lockout, rate limits, `X-Forwarded-For` spoofing, user enumeration by answer and by timing. Takes about six minutes. |
| `leak_scan.py` | Plants canary secrets through the API (passwords, tokens, the session cookie, an MFA proof, an IBAN, chat PII, a passport number in a document) and looks for each one in the database file and its log, the server log, the audit log and the responses. |
| `mitm_probe.py` | A man in the middle: an intercepting proxy between a genuine client and the API changes requests in flight (approval hash, payment id, MFA proof) and replays recorded ones; a thief uses a captured token; forged, stale and replayed provider webhooks. |
| `tls_probe.py` | The API served over HTTPS: protocol versions, HSTS, the `Secure` session cookie, plain HTTP on the TLS port, the certificate. |
| `assistant_probe.py` | Twenty hostile prompts (prompt injection, secret extraction, cross-household snooping, forced approval, SSRF and file requests, code and SQL) as parent and student; checks the reply and that nothing changed. Tests the assistant as shipped, not a real language model. |
| `prod_like_server.mjs` | Serves the built UI with the project's **real** CSP and security headers (the ones nginx applies) and proxies the API. |
| `browser_audit.mjs` | Drives real Chrome through every screen under that CSP: stored XSS in names, documents and rule reasons, hostile URLs, injected scripts and styles, framing, every network request (any third party fails the test), cookies, storage, referrers, source maps and secrets in the downloaded assets. |

## Running all of it

```bash
# 1. a lab database with two households (needs the backend venv)
cd backend
export DATA_DIR=/tmp/lab
python ../scripts/security/lab_setup.py

# 2. the API for the functional attacks (rate limits off so they do not hide other results)
RATE_LIMIT_ENABLED=false uvicorn app.main:create_app --factory --port 8002 &
python ../scripts/security/attack_probe.py http://127.0.0.1:8002 /tmp/lab

# 3. the browser audit under the production CSP
(cd ../web && npm ci && npm run build)
#    (the API must trust the audit's origin: start it with CORS_ORIGINS=http://127.0.0.1:8090,
#     or the browser sign-in is refused with 403)
node ../scripts/security/prod_like_server.mjs 8090 8002 &
node ../scripts/security/browser_audit.mjs http://127.0.0.1:8090

# 4. brute force (a fresh lab, rate limits ON, no trust in proxy headers)
DATA_DIR=/tmp/lab2 python ../scripts/security/lab_setup.py
DATA_DIR=/tmp/lab2 uvicorn app.main:create_app --factory --port 8003 --no-proxy-headers &
python ../scripts/security/brute_probe.py http://127.0.0.1:8003

# 5. the data-leak scan, the man in the middle and the assistant (against the step 2 lab and server,
#    started with its log kept: uvicorn ... > /tmp/api.log 2>&1 &)
python ../scripts/security/leak_scan.py http://127.0.0.1:8002 /tmp/lab /tmp/api.log
python ../scripts/security/mitm_probe.py http://127.0.0.1:8002 /tmp/lab
python ../scripts/security/assistant_probe.py http://127.0.0.1:8002

# 6. over TLS: a throwaway self-signed certificate (key.pem, cert.pem), then the API on 8443
uvicorn app.main:create_app --factory --port 8443 --ssl-keyfile key.pem --ssl-certfile cert.pem &
python ../scripts/security/tls_probe.py https://127.0.0.1:8443 cert.pem
```

A demo run against a second lab server needs `WEBHOOK_BASE_URL` set to that server's own address: the
simulated provider posts its signed "settled" webhook there, and the default is port 8000.

On Windows set `CHROME_PATH` if Chrome is not in `C:/Program Files/Google/Chrome/Application`.
`PASS` always means the attack was **defended**. A `FAIL` is a finding.
