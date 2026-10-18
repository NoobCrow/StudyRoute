"""Data-leak scanner for a running StudyRoute API (sandbox lab only).

It plants canary secrets through the API, then looks for each one in every place a thief or a log
reader could look: the database file (and its write-ahead log), the server log, the audit log and
the responses themselves. PASS means the canary was NOT found where it must not be.

    cd backend
    DATA_DIR=/tmp/lab python ../scripts/security/lab_setup.py
    DATA_DIR=/tmp/lab uvicorn app.main:create_app --factory --port 8002 > /tmp/api.log 2>&1 &
    python ../scripts/security/leak_scan.py http://127.0.0.1:8002 /tmp/lab /tmp/api.log

A recipient's display name is stored in plain text on purpose (the family sees it on screen). It is
reported as INFO, never hidden, and must still stay out of the log and the audit log. Uploaded
document text must NOT be in the database in plain text (it is encrypted).
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import httpx

BASE = sys.argv[1].rstrip("/")
LAB = Path(sys.argv[2])
LOG = Path(sys.argv[3])
API = BASE + "/api/v1"
PASSWORD, MFA = "Sandbox#2026", "246810"
PARENT = "parent@demo.studyroute.test"

CANARY = {
    "wrong_password": "WrongPass-CANARY-3QxZ!",
    "chat_email": "canary.person.7f3a@example.org",
    "chat_phone": "+8801799900123",
    "chat_passport": "P7Q3K9X21",
    "iban": "GB29NWBK60161331926819",
    "recipient_name": "Canary Recipient Zq9",
    "document_text": "CANARYDOC-4d9e1b7a",
    "document_filename": "CANARYFILE-5c2a8e91",
    "document_passport": "Q4W8E2R6T",
}

responses: list[str] = []


def keep(response: httpx.Response) -> None:
    response.read()
    responses.append(response.text)


client = httpx.Client(timeout=30, event_hooks={"response": [keep]})
browser = httpx.Client(timeout=30, event_hooks={"response": [keep]})  # its own cookie jar


def must(reply: httpx.Response, what: str) -> dict:
    if reply.status_code >= 400:
        sys.exit(f"setup failed at {what}: {reply.status_code} {reply.text[:200]}")
    return reply.json()


# ------------------------------------------------------------------ plant the canaries
client.post(f"{API}/auth/login", json={"email": PARENT, "password": CANARY["wrong_password"]})
login = must(client.post(f"{API}/auth/login", json={"email": PARENT, "password": PASSWORD}), "login")
access, refresh = login["access_token"], login["refresh_token"]
auth = {"Authorization": f"Bearer {access}"}

must(
    browser.post(
        f"{API}/auth/browser/login",
        headers={"X-StudyRoute-Browser": "1", "Origin": BASE},
        json={"email": PARENT, "password": PASSWORD},
    ),
    "browser login",
)
cookie = browser.cookies.get("sr_browser_session") or ""

recipient = must(
    client.post(
        f"{API}/recipients",
        headers=auth,
        json={
            "type": "UNIVERSITY",
            "display_name": CANARY["recipient_name"],
            "country": "GB",
            "bic": "EXMPGB2L",
            "iban": CANARY["iban"],
        },
    ),
    "recipient",
)
rid = recipient["recipient_id"]
proof = must(
    client.post(
        f"{API}/auth/mfa/verify",
        headers=auth,
        json={"code": MFA, "scope": "allowlist_recipient", "subject_id": rid},
    ),
    "mfa",
)["mfa_proof"]
client.patch(f"{API}/recipients/{rid}", headers={**auth, "X-MFA-Proof": proof}, json={"allowlisted": True})
must(
    client.post(
        f"{API}/documents",
        headers=auth,
        json={
            "kind": "passport",
            "filename": f"{CANARY['document_filename']}.txt",
            "content_text": f"{CANARY['document_text']} passport {CANARY['document_passport']}",
        },
    ),
    "document",
)
message = (
    f"My email is {CANARY['chat_email']}, my phone is {CANARY['chat_phone']} and my passport is "
    f"{CANARY['chat_passport']}. Plan GBP 1,000 tuition by 28 October"
)
must(client.post(f"{API}/assistant/chat", headers=auth, json={"message": message}), "chat")
for path in ("/recipients", "/documents", "/payments", "/quotes"):
    client.get(f"{API}{path}", headers=auth)
audit: dict = {"items": []}
cursor = None
while True:  # the audit log is paged (at most 100 events a page)
    page = must(client.get(f"{API}/audit/events", headers=auth, params={"limit": 100, **({"cursor": cursor} if cursor else {})}), "audit")
    audit["items"].extend(page["items"])
    cursor = page.get("next_cursor")
    if not cursor:
        break

# ------------------------------------------------------------------ the places to look
def raw(path: Path) -> bytes:
    return path.read_bytes() if path.exists() else b""


sinks = {
    "database": raw(LAB / "studyroute.db") + raw(LAB / "studyroute.db-wal") + raw(LAB / "studyroute.db-shm"),
    "server log": LOG.read_text(encoding="utf-8", errors="replace").encode("utf-8") if LOG.exists() else b"",
    "audit log": json.dumps(audit).encode("utf-8"),
    "responses": "\n".join(responses).encode("utf-8"),
}
if not sinks["database"] or not sinks["server log"]:
    sys.exit("could not read the database file or the server log: check the two paths")

# (what, the planted value, sinks where it must NOT appear, sinks where plain text is by design)
CHECKS = [
    ("the real password", PASSWORD, ("database", "server log", "audit log"), ()),
    ("a wrong password someone typed", CANARY["wrong_password"], ("database", "server log", "audit log", "responses"), ()),
    ("the access token", access, ("database", "server log", "audit log"), ()),
    ("the refresh token", refresh, ("database", "server log", "audit log"), ()),
    ("the browser session cookie", cookie, ("database", "server log", "audit log"), ()),
    ("a one-time MFA proof", proof, ("database", "server log", "audit log"), ()),
    ("the MFA code", MFA, ("database", "server log", "audit log"), ()),
    ("a full IBAN", CANARY["iban"], ("database", "server log", "audit log", "responses"), ()),
    ("an e-mail typed into the chat", CANARY["chat_email"], ("database", "server log", "audit log"), ()),
    ("a phone number typed into the chat", CANARY["chat_phone"], ("database", "server log", "audit log"), ()),
    ("a passport number typed into the chat", CANARY["chat_passport"], ("database", "server log", "audit log"), ()),
    ("a recipient's display name", CANARY["recipient_name"], ("server log", "audit log"), ("database",)),
    ("an uploaded document's text", CANARY["document_text"], ("database", "server log", "audit log"), ()),
    ("an uploaded document's file name", CANARY["document_filename"], ("server log", "audit log"), ("database",)),
    ("a passport number inside an uploaded document", CANARY["document_passport"], ("database", "server log", "audit log"), ()),
]

failures = 0
print(f"sinks: database {len(sinks['database']):,} bytes, log {len(sinks['server log']):,} bytes, "
      f"audit {len(audit.get('items', []))} events, {len(responses)} responses\n")
for what, needle, forbidden, by_design in CHECKS:
    if not needle:
        print(f"SKIP  {what}: the value was not issued")
        continue
    data = needle.encode("utf-8")
    for sink in forbidden:
        found = data in sinks[sink]
        failures += found
        print(f"{'FAIL' if found else 'PASS'}  {what} is {'IN' if found else 'not in'} the {sink}")
    for sink in by_design:
        found = data in sinks[sink]
        print(f"INFO  {what} {'is stored in plain text in' if found else 'is not stored in plain text in'} the {sink}")

# patterns that should never appear in a server log, whatever the value
log_text = sinks["server log"].decode("utf-8", errors="replace")
PATTERNS = {
    "a JWT-shaped token": r"eyJ[A-Za-z0-9_-]{15,}\.[A-Za-z0-9_-]{15,}\.[A-Za-z0-9_-]{10,}",
    "an Authorization header value": r"Authorization:\s*Bearer\s+\S+",
    "a private key": r"BEGIN (EC |RSA )?PRIVATE KEY",
    "a password hash": r"\$argon2",
    "a cookie value": r"sr_browser_session=bs_",
}
for what, pattern in PATTERNS.items():
    hit = re.search(pattern, log_text)
    failures += bool(hit)
    print(f"{'FAIL' if hit else 'PASS'}  the server log holds no {what}")

print(f"\n{'ALL CLEAR' if failures == 0 else str(failures) + ' LEAK(S) FOUND'}")
sys.exit(1 if failures else 0)
