"""A man in the middle against a running StudyRoute API (sandbox lab only).

A small intercepting proxy sits between a genuine client (the parent) and the API. It records
everything that passes, can change one request in flight, and the script then replays what it
recorded. The compose stack serves plain HTTP, so a real attacker on the network could do exactly
this: reading what is sent is NOT defended without TLS (that is risk R4, reported here as INFO);
what must hold is that changing or replaying a request does not move money.

    cd backend
    DATA_DIR=/tmp/lab python ../scripts/security/lab_setup.py
    DATA_DIR=/tmp/lab RATE_LIMIT_ENABLED=false uvicorn app.main:create_app --factory --port 8002 &
    python ../scripts/security/mitm_probe.py http://127.0.0.1:8002 /tmp/lab

PASS = the attack was defended, INFO = what an attacker on plain HTTP can learn, FAIL = a finding.
"""

from __future__ import annotations

import hashlib
import hmac
import http.server
import json
import sys
import threading
import time
import uuid
from pathlib import Path

import httpx

BASE = sys.argv[1].rstrip("/")
LAB = Path(sys.argv[2])
PASSWORD, MFA = "Sandbox#2026", "246810"
results: list[tuple[str, str, str]] = []  # (PASS | FAIL | INFO, name, detail)


def rec(name: str, ok: bool, detail: str = "") -> None:
    results.append(("PASS" if ok else "FAIL", name, detail))


def info(name: str, detail: str = "") -> None:
    results.append(("INFO", name, detail))


# ------------------------------------------------------------------ the man in the middle
class Tap:
    """An intercepting proxy: forwards to the API, records every request, may change one in flight."""

    def __init__(self, upstream: str) -> None:
        self.upstream = upstream
        self.captured: list[dict] = []
        self.mutate = None  # callable(method, path, headers, body) -> (method, path, headers, body)
        outer = self

        class Handler(http.server.BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.1"

            def log_message(self, *args) -> None:  # noqa: ANN002
                return

            def _forward(self) -> None:
                length = int(self.headers.get("Content-Length") or 0)
                body = self.rfile.read(length) if length else b""
                skip = {"host", "content-length", "connection", "accept-encoding"}
                headers = {k: v for k, v in self.headers.items() if k.lower() not in skip}
                method, path = self.command, self.path
                outer.captured.append({"method": method, "path": path, "headers": dict(headers), "body": body})
                if outer.mutate is not None:
                    method, path, headers, body = outer.mutate(method, path, dict(headers), body)
                reply = httpx.request(method, outer.upstream + path, headers=headers, content=body, timeout=30)
                self.send_response(reply.status_code)
                for key, value in reply.headers.multi_items():
                    if key.lower() not in {"content-length", "transfer-encoding", "connection", "content-encoding"}:
                        self.send_header(key, value)
                self.send_header("Content-Length", str(len(reply.content)))
                self.end_headers()
                self.wfile.write(reply.content)

            do_GET = do_POST = do_PUT = do_PATCH = do_DELETE = _forward  # noqa: N815

        self.server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.url = f"http://127.0.0.1:{self.server.server_port}"
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def seen(self, method: str, fragment: str) -> list[dict]:
        return [c for c in self.captured if c["method"] == method and fragment in c["path"]]


tap = Tap(BASE)
V = f"{tap.url}/api/v1"  # the victim talks to the API through the tap
API = f"{BASE}/api/v1"  # the attacker talks to it directly
victim = httpx.Client(timeout=30)
attacker = httpx.Client(timeout=30)


def login(client: httpx.Client, root: str, email: str) -> tuple[dict, str]:
    reply = client.post(f"{root}/auth/login", json={"email": email, "password": PASSWORD})
    assert reply.status_code == 200, reply.text
    body = reply.json()
    return body, {"Authorization": f"Bearer {body['access_token']}"}


_, admin_auth = login(attacker, API, "admin@demo.studyroute.test")
me, auth = login(victim, V, "parent@demo.studyroute.test")
user_id = me["user"]["user_id"]
attacker.put(f"{API}/kyc/mock-review", headers=admin_auth, json={"user_id": user_id, "status": "VERIFIED"})


def idem() -> dict:
    return {"Idempotency-Key": str(uuid.uuid4())}


def proof_for(scope: str, subject: str) -> str:
    reply = victim.post(f"{V}/auth/mfa/verify", headers=auth, json={"code": MFA, "scope": scope, "subject_id": subject})
    assert reply.status_code == 200, reply.text
    return reply.json()["mfa_proof"]


recipient = next(r for r in victim.get(f"{V}/recipients", headers=auth).json()["items"] if "University of Example" in r["display_name"])
rid = recipient["recipient_id"]
victim.patch(f"{V}/recipients/{rid}", headers={**auth, "X-MFA-Proof": proof_for("allowlist_recipient", rid)}, json={"allowlisted": True})
QUOTE = {"target": {"amount_minor": 1_000_000, "currency": "GBP"}, "purpose": "TUITION", "destination_country": "GB", "charge_code": "OUR"}


def pending_payment(reference: str) -> tuple[str, str]:
    quote = victim.post(f"{V}/quotes", headers=auth, json=QUOTE).json()["quote_id"]
    created = victim.post(f"{V}/payments", headers={**auth, **idem()}, json={"quote_id": quote, "provider_id": "prov_b", "recipient_id": rid, "reference": reference})
    pid = created.json()["payment_id"]
    requested = victim.post(f"{V}/payments/{pid}/request-approval", headers={**auth, **idem()}, json={})
    assert requested.status_code == 200, requested.text
    return pid, requested.json()["summary_hash"]


def state(pid: str) -> str:
    return attacker.get(f"{API}/payments/{pid}", headers=auth_direct()).json()["state"]


def auth_direct() -> dict:
    return {"Authorization": f"Bearer {me['access_token']}"}


def audit_count(pid: str, action: str) -> int:
    events = attacker.get(f"{API}/audit/events", headers=auth_direct(), params={"payment_id": pid, "limit": 100}).json()["items"]
    return sum(1 for e in events if e.get("action") == action)


def approvals(pid: str) -> int:
    """How many times the payment's own timeline shows it entering APPROVED."""
    timeline = attacker.get(f"{API}/payments/{pid}/tracker", headers=auth_direct()).json()["timeline"]
    return sum(1 for step in timeline if step["state"] == "APPROVED")


A, hash_a = pending_payment("MITM-A")
B, hash_b = pending_payment("MITM-B")

# ------------------------------------------------------------------ 1. what a man in the middle can read
seen_auth = [c for c in tap.captured if "authorization" in {k.lower() for k in c["headers"]}]
seen_login = [c for c in tap.captured if c["path"].endswith("/auth/login") and PASSWORD.encode() in c["body"]]
info("a passive listener on plain HTTP reads the sign-in password and every bearer token", f"{len(seen_login)} login(s) and {len(seen_auth)} authorised request(s) were readable")
info("TLS is what closes this (risk R4); the checks below show what still holds WITHOUT it")
stolen = next(c["headers"]["Authorization"] for c in tap.captured if "Authorization" in c["headers"])
thief = {"Authorization": stolen}

# ------------------------------------------------------------------ 2. changing a request in flight
def flip_hash(method, path, headers, body):
    if path.endswith("/approve"):
        data = json.loads(body)
        digest = data["confirm_summary_hash"]
        data["confirm_summary_hash"] = digest[:-1] + ("0" if digest[-1] != "0" else "1")
        body = json.dumps(data).encode()
    return method, path, headers, body


tap.mutate = flip_hash
reply = victim.post(f"{V}/payments/{A}/approve", headers={**auth, **idem(), "X-MFA-Proof": proof_for("approve_payment", A)}, json={"confirm_summary_hash": hash_a})
tap.mutate = None
rec("M1 a changed approval hash (what the person saw is not what is approved) is refused", reply.status_code >= 400 and state(A) == "PENDING_APPROVAL", f"{reply.status_code}, state {state(A)}")


def swap_payment(method, path, headers, body):
    return method, path.replace(f"/payments/{A}/approve", f"/payments/{B}/approve"), headers, body


tap.mutate = swap_payment
reply = victim.post(f"{V}/payments/{A}/approve", headers={**auth, **idem(), "X-MFA-Proof": proof_for("approve_payment", A)}, json={"confirm_summary_hash": hash_a})
tap.mutate = None
rec("M2 an approval redirected to another payment (proof and hash were for the first) is refused", reply.status_code >= 400 and state(B) == "PENDING_APPROVAL", f"{reply.status_code}, B is {state(B)}")


def strip_proof(method, path, headers, body):
    return method, path, {k: v for k, v in headers.items() if k.lower() != "x-mfa-proof"}, body


tap.mutate = strip_proof
reply = victim.post(f"{V}/payments/{A}/approve", headers={**auth, **idem(), "X-MFA-Proof": proof_for("approve_payment", A)}, json={"confirm_summary_hash": hash_a})
tap.mutate = None
rec("M3 an approval whose MFA proof was stripped in transit is refused", reply.status_code == 403 and state(A) == "PENDING_APPROVAL", f"{reply.status_code}")

wrong_scope = proof_for("allowlist_recipient", rid)


def wrong_proof(method, path, headers, body):
    headers = {k: v for k, v in headers.items() if k.lower() != "x-mfa-proof"}
    headers["X-MFA-Proof"] = wrong_scope
    return method, path, headers, body


tap.mutate = wrong_proof
reply = victim.post(f"{V}/payments/{A}/approve", headers={**auth, **idem(), "X-MFA-Proof": proof_for("approve_payment", A)}, json={"confirm_summary_hash": hash_a})
tap.mutate = None
rec("M4 an approval with another action's MFA proof swapped in is refused", reply.status_code >= 400 and state(A) == "PENDING_APPROVAL", f"{reply.status_code}")

# ------------------------------------------------------------------ 3. what a thief with the captured token can do
reply = attacker.post(f"{API}/payments/{A}/approve", headers={**thief, **idem()}, json={"confirm_summary_hash": hash_a})
rec("M5 a stolen bearer token cannot approve a payment without an MFA proof", reply.status_code == 403 and state(A) == "PENDING_APPROVAL", f"{reply.status_code}")
reply = attacker.patch(f"{API}/recipients/{rid}", headers=thief, json={"allowlisted": False})
rec("M6 a stolen bearer token cannot de-list or allowlist a recipient without an MFA proof", reply.status_code == 403, f"{reply.status_code}")
evil = attacker.post(f"{API}/recipients", headers=thief, json={"type": "UNIVERSITY", "display_name": "Attacker Account", "country": "GB", "bic": "EXMPGB2L", "iban": "GB29NWBK60161331926819"})
evil_rid = evil.json().get("recipient_id") if evil.status_code < 300 else None
if evil_rid:
    quote = attacker.post(f"{API}/quotes", headers=thief, json=QUOTE).json()["quote_id"]
    draft = attacker.post(f"{API}/payments", headers={**thief, **idem()}, json={"quote_id": quote, "provider_id": "prov_b", "recipient_id": evil_rid, "reference": "ATTACKER"})
    evil_pid = draft.json().get("payment_id")
    ask = attacker.post(f"{API}/payments/{evil_pid}/request-approval", headers={**thief, **idem()}, json={}) if evil_pid else None
    rec("M7 a payment to the thief's own recipient cannot even be put up for approval (not allowlisted)", ask is not None and ask.status_code >= 400, f"{ask.status_code if ask else 'no draft'}")
else:
    rec("M7 the thief cannot add a recipient to pay", True, f"{evil.status_code}")
read = attacker.get(f"{API}/payments", headers=thief)
info("a thief holding a captured token can READ the family's payments until the token expires (15 minutes)", f"GET /payments -> {read.status_code}; this is why TLS matters")
cancel = attacker.post(f"{API}/payments/{B}/cancel", headers={**thief, **idem()})
info("a thief holding a captured token can cancel a pending draft (no money moves)", f"POST cancel -> {cancel.status_code}")

# ------------------------------------------------------------------ 4. replaying what was recorded
good_proof = proof_for("approve_payment", A)
good_key = str(uuid.uuid4())
done = victim.post(f"{V}/payments/{A}/approve", headers={**auth, "Idempotency-Key": good_key, "X-MFA-Proof": good_proof}, json={"confirm_summary_hash": hash_a})
rec("M8 the genuine approval (control) succeeds", done.status_code == 200 and state(A) in {"APPROVED", "SUBMITTED", "SETTLED"}, f"{done.status_code}, state {state(A)}")
captured = tap.seen("POST", f"/payments/{A}/approve")[-1]
replay = httpx.post(BASE + captured["path"], headers=captured["headers"], content=captured["body"], timeout=30)
rec("M9 replaying the recorded approval exactly (same key, same proof) makes no second approval", approvals(A) == 1, f"{replay.status_code}, approvals on the timeline: {approvals(A)}")
fresh = {**captured["headers"], "Idempotency-Key": str(uuid.uuid4())}
replay2 = httpx.post(BASE + captured["path"], headers=fresh, content=captured["body"], timeout=30)
rec("M10 replaying it with a new Idempotency-Key is refused (the MFA proof is single-use)", replay2.status_code >= 400 and approvals(A) == 1, f"{replay2.status_code}")

# ------------------------------------------------------------------ 5. forging and replaying the provider's webhook
secrets = json.loads((LAB / "dev_secrets.json").read_text(encoding="utf-8"))
deadline = time.time() + 30
uetr = None
while time.time() < deadline and not uetr:
    uetr = attacker.get(f"{API}/payments/{A}/tracker", headers=auth_direct()).json().get("uetr")
    time.sleep(1)


def signed(secret: str, body: bytes, when: int) -> dict:
    digest = hmac.new(secret.encode(), f"{when}.".encode() + body, hashlib.sha256).hexdigest()
    return {"X-Signature": f"t={when},v1={digest}", "X-Event-Id": f"evt-{uuid.uuid4().hex[:16]}", "Content-Type": "application/json"}


if uetr:
    body = json.dumps({"event": "payment.settled", "payment_id": A, "uetr": uetr}).encode()
    other = json.dumps({"event": "payment.failed", "payment_id": A, "uetr": uetr}).encode()
    now = int(time.time())
    key_b, key_a = secrets["WEBHOOK_SECRET_PROV_B"], secrets["WEBHOOK_SECRET_PROV_A"]
    reply = httpx.post(f"{API}/webhooks/provider", headers=signed(key_b, body, now), content=other, timeout=30)
    rec("M11 a webhook whose body was changed after signing is refused", reply.status_code == 401, str(reply.status_code))
    reply = httpx.post(f"{API}/webhooks/provider", headers=signed(key_b, body, now - 3600), content=body, timeout=30)
    rec("M12 a correctly signed but old webhook (replayed an hour later) is refused", reply.status_code == 401, str(reply.status_code))
    reply = httpx.post(f"{API}/webhooks/provider", headers=signed(key_a, body, now), content=body, timeout=30)
    rec("M13 a webhook signed by a different provider cannot change this provider's payment", state(A) != "FAILED" and audit_count(A, "webhook.accepted") == 0 or reply.status_code >= 400, f"{reply.status_code}, state {state(A)}")
    genuine = signed(key_b, body, now)
    first = httpx.post(f"{API}/webhooks/provider", headers=genuine, content=body, timeout=30)
    accepted = audit_count(A, "webhook.accepted")
    second = httpx.post(f"{API}/webhooks/provider", headers=genuine, content=body, timeout=30)
    rec("M14 replaying a genuine webhook (same event id) has no second effect", audit_count(A, "webhook.accepted") == accepted and accepted <= 1, f"first {first.status_code}, replay {second.status_code} {second.text[:60]}")
else:
    info("webhook checks skipped: the payment had no UETR within 30 seconds")

# ------------------------------------------------------------------ report
tap.server.shutdown()
for kind, name, detail in results:
    print(f"{kind:4}  {name}{'  -> ' + detail if detail and kind != 'PASS' else ''}")
passed = sum(1 for k, _, _ in results if k == "PASS")
failed = sum(1 for k, _, _ in results if k == "FAIL")
print(f"\n{passed} defended, {failed} failed, {sum(1 for k, _, _ in results if k == 'INFO')} informational")
sys.exit(1 if failed else 0)
