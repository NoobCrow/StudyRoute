"""Black-box attack probe against a running StudyRoute API (sandbox lab, two households).

PASS means the attack was DEFENDED.

    cd backend
    DATA_DIR=/tmp/lab python ../scripts/security/lab_setup.py
    DATA_DIR=/tmp/lab RATE_LIMIT_ENABLED=false uvicorn app.main:create_app --factory --port 8002 &
    python ../scripts/security/attack_probe.py http://127.0.0.1:8002 /tmp/lab

The lab data dir must hold dev_secrets.json (the probe forges tokens with it to prove they fail).
It creates records in the lab database, so never point it at data you care about.
"""
from __future__ import annotations

import base64
import json
import re
import sys
import time
import uuid
from datetime import date, timedelta

import httpx
import jwt as pyjwt
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec

BASE = sys.argv[1].rstrip("/")
LAB = sys.argv[2]
API = BASE + "/api/v1"
PASSWORD = "Sandbox#2026"
MFA = "246810"
results: list[tuple[str, bool, str]] = []
bodies: list[tuple[str, str]] = []  # (request label, response text) for the leakage scan
all_headers: list[tuple[str, dict]] = []


def rec(name: str, ok: bool, detail: str = "") -> None:
    results.append((name, bool(ok), detail))


def hook(response: httpx.Response) -> None:
    response.read()
    label = f"{response.request.method} {response.request.url.path}"
    bodies.append((label, response.text))
    all_headers.append((label, dict(response.headers)))


client = httpx.Client(timeout=30, event_hooks={"response": [hook]})


class User:
    def __init__(self, email: str):
        self.email = email
        reply = client.post(f"{API}/auth/login", json={"email": email, "password": PASSWORD})
        assert reply.status_code == 200, (email, reply.text)
        body = reply.json()
        self.access, self.refresh, self.id = body["access_token"], body["refresh_token"], body["user"]["user_id"]

    def h(self, **extra):
        return {"Authorization": f"Bearer {self.access}", **extra}

    def call(self, method, path, *, json_body=None, idem=None, mfa=None, params=None, headers=None):
        hdr = self.h(**(headers or {}))
        if idem:
            hdr["Idempotency-Key"] = idem if isinstance(idem, str) else str(uuid.uuid4())
        if mfa:
            hdr["X-MFA-Proof"] = mfa
        return client.request(method, f"{API}{path}", headers=hdr, json=json_body, params=params)

    def proof(self, scope, subject):
        reply = self.call("POST", "/auth/mfa/verify", json_body={"code": MFA, "scope": scope, "subject_id": subject})
        assert reply.status_code == 200, reply.text
        return reply.json()["mfa_proof"]


def no_data(reply: httpx.Response, *secrets: str) -> bool:
    return not any(s and s in reply.text for s in secrets)


import hashlib
import hmac


def b64(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()


def hs256(payload: dict, key: bytes) -> str:
    """A hand-made HS256 token, the way an attacker would build it (the library refuses to)."""
    head = b64(json.dumps({"alg": "HS256", "typ": "JWT"}).encode())
    body = b64(json.dumps(payload).encode())
    sig = hmac.new(key, f"{head}.{body}".encode(), hashlib.sha256).digest()
    return f"{head}.{body}.{b64(sig)}"


# ------------------------------------------------------------------ setup
p1, s1, adm = User("parent@demo.studyroute.test"), User("student@demo.studyroute.test"), User("admin@demo.studyroute.test")
p2, s2 = User("parent2@lab.studyroute.test"), User("student2@lab.studyroute.test")
client.put(f"{API}/kyc/mock-review", headers=adm.h(), json={"user_id": p1.id, "status": "VERIFIED"})

uni1 = next(r for r in p1.call("GET", "/recipients").json()["items"] if "University of Example" in r["display_name"])["recipient_id"]
uni2 = p2.call("GET", "/recipients").json()["items"][0]["recipient_id"]
quote_body = {"target": {"amount_minor": 1_000_000, "currency": "GBP"}, "purpose": "TUITION", "destination_country": "GB", "charge_code": "OUR"}
q1 = p1.call("POST", "/quotes", json_body=quote_body).json()["quote_id"]
q2 = p2.call("POST", "/quotes", json_body=quote_body).json()["quote_id"]
pay1 = p1.call("POST", "/payments", idem=True, json_body={"quote_id": q1, "provider_id": "prov_b", "recipient_id": uni1, "reference": "INV-H1-SECRET-REF"}).json()["payment_id"]
first = (date.today() + timedelta(days=3)).isoformat()
esc_body = lambda rid, ref: {"recipient_id": rid, "purpose": "TUITION", "total": {"amount_minor": 1_000_000, "currency": "GBP"}, "tranches": 1, "first_release": first, "cadence": "ONCE", "reference": ref}
KEY = str(uuid.uuid4())
e1 = p1.call("POST", "/escrows", idem=KEY, json_body=esc_body(uni1, "H1-SECRET-ESCROW")).json()["escrow_id"]
doc1 = p1.call("POST", "/documents", json_body={"kind": "passport", "filename": "h1-secret-passport.txt", "content_text": "H1 SECRET DOCUMENT BODY"}).json()["document_id"]
acc1 = p1.call("GET", "/bank/accounts").json()["items"]
tr1 = p1.call("POST", "/bank/transfers", idem=True, json_body={"source": acc1[0]["number"], "destination": "SBX-B-0002", "amount": {"amount_minor": 50_000, "currency": "BDT"}, "reference": "H1-SECRET-TRANSFER"}).json().get("id")
h1_secrets = ["INV-H1-SECRET-REF", "H1-SECRET-ESCROW", "h1-secret-passport", "H1 SECRET DOCUMENT BODY", "H1-SECRET-TRANSFER", "parent@demo.studyroute.test", "GB08EXMP12345612344821"]

# ------------------------------------------------------------------ 1. every route, no token
spec = client.get(f"{API}/openapi.json")
paths = spec.json()["paths"] if spec.status_code == 200 else {}
public = {"/auth/login", "/auth/refresh", "/auth/logout", "/health", "/sandbox", "/webhooks/provider"}
leaks, five_hundreds, swept = [], [], 0
for path, ops in paths.items():
    for method in ops:
        if method.lower() not in {"get", "post", "put", "patch", "delete"}:
            continue
        url = f"{API}{re.sub(r'{[^}]+}', 'x', path)}"
        reply = client.request(method.upper(), url, json={} if method != "get" else None)
        swept += 1
        if reply.status_code >= 500:
            five_hundreds.append(f"{method.upper()} {path} {reply.status_code}")
        if path in public:
            continue
        if reply.status_code < 400:
            leaks.append(f"{method.upper()} {path} -> {reply.status_code}")
rec(f"1.1 all {swept} routes refuse an anonymous caller", spec.status_code == 200 and not leaks, "; ".join(leaks[:5]) or f"{len(paths)} paths")
rec("1.2 no anonymous request causes a server error (500)", not five_hundreds, "; ".join(five_hundreds[:5]))

# ------------------------------------------------------------------ 2. token forgery
secrets = json.load(open(f"{LAB}/dev_secrets.json", encoding="utf-8"))
pem_key = next((v for k, v in secrets.items() if "private" in k.lower() and "PRIVATE KEY" in str(v)), None)
claims = pyjwt.decode(p1.access, options={"verify_signature": False})
pub_pem = serialization.load_pem_private_key(pem_key.encode(), None).public_key().public_bytes(
    serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo) if pem_key else b""
admin_claims = {**claims, "role": "admin", "kind": "admin", "sub": adm.id}
none_token = base64.urlsafe_b64encode(json.dumps({"alg": "none", "typ": "JWT"}).encode()).rstrip(b"=").decode() + "." + base64.urlsafe_b64encode(json.dumps(admin_claims).encode()).rstrip(b"=").decode() + "."
attacker_key = ec.generate_private_key(ec.SECP256R1())
forged = {
    "alg=none": none_token,
    "HS256 signed with the public key (algorithm confusion)": hs256(admin_claims, pub_pem),
    "ES256 signed with an attacker's own key": pyjwt.encode(admin_claims, attacker_key, algorithm="ES256"),
    "valid token with the signature cut off": p1.access.rsplit(".", 1)[0] + ".",
    "valid header and claims, flipped signature": p1.access[:-4] + ("AAAA" if not p1.access.endswith("AAAA") else "BBBB"),
    "expired token": pyjwt.encode({**claims, "exp": int(time.time()) - 3600}, attacker_key, algorithm="ES256"),
    "refresh token used as an access token": p1.refresh,
    "empty bearer": "",
    "random garbage": "Bearer.Bearer.Bearer",
}
for label, token in forged.items():
    reply = client.get(f"{API}/audit/verify", headers={"Authorization": f"Bearer {token}" if token else "Bearer"})
    rec(f"2.x forged token refused: {label}", reply.status_code == 401, str(reply.status_code))
reply = client.get(f"{API}/payments", params={"access_token": p1.access})
rec("2.y a token in the URL query string is ignored", reply.status_code == 401, str(reply.status_code))
reply = client.get(f"{API}/payments", headers={"Authorization": f"Basic {base64.b64encode(b'a:b').decode()}"})
rec("2.z a non-Bearer scheme is refused", reply.status_code == 401, str(reply.status_code))

# ------------------------------------------------------------------ 3. one household reading another
def blocked(label, reply, *must_not_contain):
    ok = reply.status_code in (401, 403, 404, 422) and no_data(reply, *must_not_contain)
    rec(label, ok, f"{reply.status_code}")


for who, name in ((p2, "parent2"), (s2, "student2")):
    blocked(f"3.1 {name} cannot read household 1's payment", who.call("GET", f"/payments/{pay1}"), *h1_secrets)
    blocked(f"3.2 {name} cannot read household 1's payment tracker", who.call("GET", f"/payments/{pay1}/tracker"), *h1_secrets)
    blocked(f"3.3 {name} cannot read household 1's compliance report", who.call("GET", f"/payments/{pay1}/compliance-report"), *h1_secrets)
    blocked(f"3.4 {name} cannot read household 1's instruction preview", who.call("GET", f"/payments/{pay1}/instruction-preview"), *h1_secrets)
    blocked(f"3.5 {name} cannot read household 1's quote", who.call("GET", f"/quotes/{q1}"))
    blocked(f"3.6 {name} cannot read household 1's escrow", who.call("GET", f"/escrows/{e1}"), *h1_secrets)
    blocked(f"3.7 {name} cannot see household 1's bank transfer", who.call("GET", f"/bank/transfers/{tr1}"), *h1_secrets)
    blocked(f"3.8 {name} cannot see household 1's statement", who.call("GET", f"/bank/accounts/{acc1[0]['id']}/statement"), *h1_secrets)
for label, reply in (
    ("3.9 parent2 cannot rename household 1's recipient", p2.call("PATCH", f"/recipients/{uni1}", json_body={"display_name": "Hacked"})),
    ("3.10 parent2 cannot cancel household 1's payment", p2.call("POST", f"/payments/{pay1}/cancel", idem=True)),
    ("3.11 parent2 cannot request approval of household 1's payment", p2.call("POST", f"/payments/{pay1}/request-approval", idem=True)),
    ("3.12 parent2 cannot confirm household 1's escrow even with a proof for it", p2.call("POST", f"/escrows/{e1}/confirm", idem=True, mfa=p1.proof("confirm_escrow", e1))),
    ("3.13 parent2 cannot abandon household 1's escrow", p2.call("POST", f"/escrows/{e1}/abandon", idem=True)),
    ("3.14 parent2 cannot cancel household 1's escrow", p2.call("POST", f"/escrows/{e1}/cancel", idem=True)),
    ("3.15 parent2 cannot delete household 1's document", p2.call("DELETE", f"/documents/{doc1}")),
    ("3.16 parent2 cannot confirm household 1's bank transfer", p2.call("POST", f"/bank/transfers/{tr1}/confirm", idem=True)),
):
    blocked(label, reply, *h1_secrets)
# an MFA proof is bound to the user: a proof minted by household 1 does not work for household 2
reply = p2.call("POST", f"/escrows/{e1}/confirm", idem=True, mfa=p1.proof("confirm_escrow", e1))
rec("3.17 a stolen MFA proof does not work for another user", reply.status_code in (403, 404), str(reply.status_code))
reply = p2.call("POST", "/auth/mfa/verify", json_body={"code": MFA, "scope": "confirm_escrow", "subject_id": e1})
rec("3.18 cannot even mint a proof for someone else's escrow", reply.status_code == 404, str(reply.status_code))
# lists contain only your own household
mine = json.dumps([p2.call("GET", p).json() for p in ("/payments", "/recipients", "/documents", "/escrows", "/quotes", "/bank/accounts", "/bank/transfers", "/audit/events?limit=100")])
rec("3.19 household 2's lists contain nothing of household 1", no_data(type("R", (), {"text": mine})(), *h1_secrets, p1.id, pay1, e1, q1, uni1, doc1), "")
rec("3.20 household 2's audit view has none of household 1's events", p1.id not in mine and pay1 not in mine, "")
# a student cannot do parent-only things in their own household
for label, reply in (
    ("3.21 student cannot approve", s1.call("POST", f"/payments/{pay1}/approve", idem=True, json_body={"confirm_summary_hash": "x" * 64})),
    ("3.22 student cannot lock escrow funds", s1.call("POST", f"/escrows/{e1}/confirm", idem=True)),
    ("3.23 student cannot allowlist a recipient", s1.call("PATCH", f"/recipients/{uni1}", json_body={"allowlisted": True})),
    ("3.24 student cannot reset the household's data", s1.call("POST", "/me/reset")),
    ("3.25 student cannot confirm a bank transfer", s1.call("POST", f"/bank/transfers/{tr1}/confirm", idem=True)),
):
    blocked(label, reply)

# ------------------------------------------------------------------ 4. privilege escalation
esc_targets = [
    ("PUT", "/config/rules", {"key": "limits.per_transaction_usd_equivalent", "value": 99999999, "reason": "evil"}),
    ("PUT", "/kyc/mock-review", {"user_id": p1.id, "status": "VERIFIED"}),
    ("POST", "/chain/anchor", None),
    ("GET", "/chain/verify", None),
    ("POST", "/chain/sandbox/advance", {"days": 30}),
    ("POST", f"/escrows/{e1}/freeze", {"reason": "evil freeze"}),
    ("POST", f"/escrows/{e1}/tranches/0/sandbox-refund", None),
    ("POST", f"/sandbox/payments/{pay1}/provider-event", {"event": "settled"}),
    ("GET", "/audit/verify", None),
]
for who, name in ((p1, "parent"), (s1, "student")):
    for method, path, body in esc_targets:
        reply = who.call(method, path, json_body=body)
        rec(f"4.x {name} refused: {method} {path.split('/')[1]}{'/..' if path.count('/') > 2 else ''}", reply.status_code in (403, 404), str(reply.status_code))
ai_reply = client.post(f"{API}/auth/login", json={"email": "ai@demo.studyroute.test", "password": PASSWORD})
rec("4.y the AI service account cannot sign in", ai_reply.status_code in (400, 401, 403, 422), str(ai_reply.status_code))

# ------------------------------------------------------------------ 5. injection and hostile input
SQLI = ["' OR '1'='1", "'; DROP TABLE users;--", "\" OR \"\"=\"", "1; SELECT * FROM users", "' UNION SELECT password_hash,2,3 FROM users--", "admin'--", "\\' OR 1=1 #"]
statuses, error_text = [], []
def watch(reply):
    statuses.append(reply.status_code)
    if re.search(r"Traceback|sqlite|sqlalchemy|OperationalError|syntax error|\.py\"|File \"", reply.text, re.I):
        error_text.append(reply.text[:120])
for payload in SQLI:
    for path, params in (("/audit/events", {"action": payload}), ("/audit/events", {"payment_id": payload}), ("/payments", {"limit": payload}), ("/payments", {"cursor": payload}),
                         ("/planner/deadline", {"country": payload, "due_date": "2026-12-01"}), ("/checklist", {"country": "GB", "purpose": payload}), ("/rates/history", {"currency": payload})):
        watch(adm.call("GET", path, params=params))
    watch(p1.call("POST", "/recipients", json_body={"type": "UNIVERSITY", "display_name": payload, "country": "GB", "bic": "EXMPGB2L", "iban": "GB08EXMP12345612344821"}))
    watch(p1.call("POST", "/documents", json_body={"kind": "passport", "filename": payload, "content_text": payload}))
    watch(p1.call("POST", "/auth/mfa/verify", json_body={"code": payload, "scope": "confirm_escrow", "subject_id": payload}))
    watch(client.post(f"{API}/auth/login", json={"email": payload, "password": payload}))
rec("5.1 SQL-injection strings cause no server error", all(s < 500 for s in statuses), f"{len(statuses)} requests, worst {max(statuses)}")
rec("5.2 no database error, path or stack trace appears in any response", not error_text, "; ".join(error_text[:2]))
still_ok = client.post(f"{API}/auth/login", json={"email": "parent@demo.studyroute.test", "password": PASSWORD}).status_code == 200 and len(p1.call("GET", "/recipients").json()["items"]) >= 1
rec("5.3 after the barrage logins and recipients still work (nothing was dropped)", still_ok, "")
xss = "<img src=x onerror=alert(document.domain)>"
made = p1.call("POST", "/recipients", json_body={"type": "UNIVERSITY", "display_name": xss, "country": "GB", "bic": "EXMPGB2L", "iban": "GB82WEST12345698765432"})
rec("5.4 script text in a name is stored as inert data, served as JSON with nosniff", made.status_code in (201, 422) and made.headers["content-type"].startswith("application/json") and made.headers.get("x-content-type-options") == "nosniff", f"{made.status_code}")
for label, reply in (
    ("5.5 an escrow reference with markup is refused", p1.call("POST", "/escrows", idem=True, json_body=esc_body(uni1, "<script>alert(1)</script>"))),
    ("5.6 a freeze reason is length-limited", adm.call("POST", f"/escrows/{e1}/freeze", json_body={"reason": "x" * 5000})),
):
    rec(label, reply.status_code in (400, 422), str(reply.status_code))
big = client.post(f"{API}/auth/login", content=b'{"email":"' + b"A" * 3_000_000 + b'"}', headers={"Content-Type": "application/json"})
rec("5.7 a 3 MB body is refused (413) before it is parsed", big.status_code == 413, str(big.status_code))
deep = client.post(f"{API}/quotes", headers=p1.h(**{"Content-Type": "application/json"}), content=b"[" * 200_000 + b"]" * 200_000)
rec("5.8 200,000-deep JSON nesting does not crash the server", deep.status_code in (400, 413, 422), str(deep.status_code))
bad_utf = client.post(f"{API}/auth/login", content=b'{"email":"\xff\xfe","password":"x"}', headers={"Content-Type": "application/json"})
rec("5.9 invalid UTF-8 is a clean 4xx", 400 <= bad_utf.status_code < 500, str(bad_utf.status_code))
nul = p1.call("POST", "/documents", json_body={"kind": "passport", "filename": "a\u0000b", "content_text": "x\u0000y"})
rec("5.10 NUL bytes do not break storage", nul.status_code < 500, str(nul.status_code))
bad_json = client.post(f"{API}/auth/login", content=b"{not json", headers={"Content-Type": "application/json"})
rec("5.11 malformed JSON is a clean 4xx", 400 <= bad_json.status_code < 500, str(bad_json.status_code))
mass = p1.call("POST", "/recipients", json_body={"type": "UNIVERSITY", "display_name": "x", "country": "GB", "bic": "EXMPGB2L", "iban": "GB82WEST12345698765432", "owner_id": p2.id, "allowlisted": True, "role": "admin"})
rec("5.12 mass assignment (extra owner_id, allowlisted, role) is refused", mass.status_code == 422, str(mass.status_code))
mass2 = p1.call("POST", "/escrows", idem=True, json_body={**esc_body(uni1, "x1"), "owner_id": p2.id, "status": "ON_CHAIN", "chain_escrow_id": 1})
rec("5.13 mass assignment on escrows is refused", mass2.status_code == 422, str(mass2.status_code))
trav = [client.get(f"{API}/payments/..%2f..%2fhealth", headers=p1.h()), client.get(f"{API}/escrows/%2e%2e%2f%2e%2e%2fhealth", headers=p1.h()), client.get(f"{BASE}/../../etc/passwd"), client.get(f"{API}/payments/{'A' * 5000}", headers=p1.h())]
rec("5.14 path traversal and absurdly long ids give clean 4xx", all(400 <= r.status_code < 500 for r in trav), str([r.status_code for r in trav]))

# ------------------------------------------------------------------ 6. protocol-level
tr = client.request("TRACE", f"{API}/health")
rec("6.1 TRACE is not allowed", tr.status_code in (405, 404, 501), str(tr.status_code))
evil = {"Origin": "https://evil.example"}
pre = client.options(f"{API}/payments", headers={**evil, "Access-Control-Request-Method": "GET", "Access-Control-Request-Headers": "authorization"})
get = client.get(f"{API}/health", headers=evil)
rec("6.2 a CORS preflight from an evil origin is not approved", "access-control-allow-origin" not in {k.lower() for k in pre.headers} or pre.headers.get("access-control-allow-origin") not in ("*", "https://evil.example"), str(dict(pre.headers).get("access-control-allow-origin")))
rec("6.3 a normal request from an evil origin gets no allow-origin header", "access-control-allow-origin" not in {k.lower() for k in get.headers}, "")
rec("6.4 credentials are never allowed cross-origin", "access-control-allow-credentials" not in {k.lower() for k in get.headers} and "access-control-allow-credentials" not in {k.lower() for k in pre.headers}, "")
hook_ = client.post(f"{API}/webhooks/provider", content=b'{"payment_id":"x","event":"settled"}', headers={"Content-Type": "application/json"})
rec("6.5 a webhook with no signature is refused", hook_.status_code in (400, 401, 403), str(hook_.status_code))
hook2 = client.post(f"{API}/webhooks/provider", content=b'{"payment_id":"x","event":"settled"}', headers={"Content-Type": "application/json", "X-Signature": "sha256=" + "0" * 64, "X-Timestamp": str(int(time.time())), "X-Provider": "prov_b"})
rec("6.6 a webhook with a forged signature is refused", hook2.status_code in (400, 401, 403), str(hook2.status_code))
crlf = client.get(f"{API}/health", headers={"X-Request-ID": "abc def\t<script>" + "z" * 300})
rec("6.7 a hostile X-Request-ID is replaced, never reflected", "<script>" not in json.dumps(dict(crlf.headers)), crlf.headers.get("x-request-id", ""))
# idempotency keys are scoped to the caller: another user reusing a key never receives the first user's answer
other = p2.call("POST", "/escrows", idem=KEY, json_body=esc_body(uni2, "H2-OWN-ESCROW"))
rec("6.8 reusing someone else's Idempotency-Key does not replay their response", other.status_code == 201 and e1 not in other.text and "H1-SECRET" not in other.text, f"{other.status_code}")
same = p1.call("POST", "/escrows", idem=KEY, json_body=esc_body(uni1, "DIFFERENT BODY"))
rec("6.9 the same user reusing a key with a different body is refused", same.status_code == 422, str(same.status_code))

# ------------------------------------------------------------------ 7. what leaves the server
blob_checks = {
    "a password hash": r"\$argon2",
    "an MFA secret field": r"mfa_secret",
    "the encrypted-account field": r"iban_or_account_enc",
    "a private key": r"BEGIN (EC |RSA )?PRIVATE KEY",
    "a full IBAN of a recipient": r"\bGB(08|82|13)[A-Z]{4}\d{14}\b",
    "the refresh-token family or token hash": r"token_hash|refresh_hash|family_id",
    "a database file path": r"studyroute\.db|\.sqlite",
}
for label, pattern in blob_checks.items():
    hits = [l for l, text in bodies if re.search(pattern, text)]
    rec(f"7.1 no response ever contains {label}", not hits, "; ".join(hits[:3]))
cookie_hits = [l for l, h in all_headers if "set-cookie" in {k.lower() for k in h}]
rec("7.3 the server never sets a cookie (nothing to track a browser with)", not cookie_hits, "; ".join(cookie_hits[:3]))
ver = {h.get("server", "") for _, h in all_headers}
rec("7.4 the Server header discloses no version", all(not re.search(r"\d", v) for v in ver), ", ".join(ver))
for needed in ("x-content-type-options", "x-frame-options", "referrer-policy", "content-security-policy", "permissions-policy", "strict-transport-security", "cache-control"):
    missing = [l for l, h in all_headers if needed not in {k.lower() for k in h}]
    rec(f"7.5 every response carries {needed}", not missing, "; ".join(missing[:3]))
auth_cache = [h.get("cache-control") for l, h in all_headers if "auth" in l or "payments" in l or "escrows" in l]
rec("7.6 API responses are no-store (never cached by a browser or proxy)", all(c and "no-store" in c for c in auth_cache), str(set(auth_cache)))

passed = sum(1 for _, ok, _ in results if ok)
for name, ok, detail in results:
    print(f"{'PASS' if ok else 'FAIL'}  {name}{'' if ok else '  -> ' + detail}")
print(f"\n{passed}/{len(results)} defended; {len(bodies)} responses captured")
