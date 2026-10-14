"""Brute-force, lockout, rate-limit and user-enumeration probes. Takes about six minutes (it waits
out rate-limit windows).

    DATA_DIR=/tmp/lab2 python ../scripts/security/lab_setup.py
    DATA_DIR=/tmp/lab2 uvicorn app.main:create_app --factory --port 8003 --no-proxy-headers &
    python ../scripts/security/brute_probe.py http://127.0.0.1:8003

Start the server with --no-proxy-headers: uvicorn otherwise trusts X-Forwarded-For from loopback,
which is the right behaviour behind nginx but would hide the spoofing check from a local test.
"""
import statistics
import sys
import time

import httpx

BASE = sys.argv[1].rstrip("/") + "/api/v1"
results = []
def rec(name, ok, detail=""):
    results.append((name, bool(ok), detail))

c = httpx.Client(timeout=30)
def login(email, password, **hdr):
    return c.post(f"{BASE}/auth/login", json={"email": email, "password": password}, headers=hdr)

# --- user enumeration: unknown user and wrong password must look identical
unknown = login("nobody@nowhere.test", "wrong-password")
known = login("parent2@lab.studyroute.test", "wrong-password")
rec("1 unknown user and wrong password return the same status and message",
    unknown.status_code == known.status_code and unknown.json().get("detail") == known.json().get("detail"),
    f"{unknown.status_code}/{known.status_code}: {unknown.json().get('detail')!r} vs {known.json().get('detail')!r}")

# --- timing: an unknown user still costs one password hash (no fast path to enumerate accounts)
def timed(email, n=4):
    out = []
    for _ in range(n):
        t = time.perf_counter(); login(email, "x" * 12); out.append(time.perf_counter() - t)
    return statistics.median(out)

time.sleep(61)  # let the IP rate window clear after the two calls above
ta, tb = timed("nobody2@nowhere.test"), timed("student2@lab.studyroute.test")
rec("2 response time does not reveal whether an account exists", abs(ta - tb) < max(ta, tb) * 0.5 + 0.05, f"unknown {ta*1000:.0f} ms, known {tb*1000:.0f} ms")
time.sleep(61)

# --- the rate limit is per socket address: a spoofed X-Forwarded-For does not reset it
codes = [login("nobody@nowhere.test", "x", **{"X-Forwarded-For": f"10.0.{i}.{i}"}).status_code for i in range(14)]
rec("3 a burst of logins gets 429, and forging X-Forwarded-For does not bypass it", 429 in codes, str(codes))
retry = login("nobody@nowhere.test", "x", **{"X-Forwarded-For": "8.8.8.8"})
rec("3b the 429 carries Retry-After and a problem body", retry.status_code == 429 and "retry-after" in {k.lower() for k in retry.headers}, str(retry.status_code))
time.sleep(61)

# --- account lockout after repeated wrong passwords (spread over time so the IP limit does not hide it)
statuses = []
for i in range(6):
    statuses.append(login("student2@lab.studyroute.test", f"wrong-{i}").status_code)
    time.sleep(0.2)
right = login("student2@lab.studyroute.test", "Sandbox#2026")
rec("4 after repeated wrong passwords even the right password is refused (account locked)", right.status_code in (401, 403, 429), f"{statuses} then {right.status_code}")
time.sleep(61)  # a fresh per-IP window, so the answer comes from the failure counter, not the IP limit
ghost = login("nobody-4b@nowhere.test", "x")
for _ in range(6):
    ghost = login("nobody-4b@nowhere.test", "x")
rec("4b a locked REAL account and a made-up address give the identical answer (no way to discover accounts)",
    right.status_code == ghost.status_code == 429 and right.json().get("detail") == ghost.json().get("detail"),
    f"{right.status_code}/{ghost.status_code}: {right.json().get('detail')!r} vs {ghost.json().get('detail')!r}")
time.sleep(61)

# --- MFA lockout
tok = login("parent2@lab.studyroute.test", "Sandbox#2026").json()["access_token"]
h = {"Authorization": f"Bearer {tok}"}
subject = c.get(f"{BASE}/recipients", headers=h).json()["items"][0]["recipient_id"]
codes = []
for i in range(7):
    codes.append(c.post(f"{BASE}/auth/mfa/verify", headers=h, json={"code": f"00000{i}", "scope": "allowlist_recipient", "subject_id": subject}).status_code)
good = c.post(f"{BASE}/auth/mfa/verify", headers=h, json={"code": "246810", "scope": "allowlist_recipient", "subject_id": subject})
rec("5 repeated wrong MFA codes lock MFA, so the right code is then refused", good.status_code in (403, 429), f"{codes} then {good.status_code}")

# --- per-user write limits
time.sleep(61)
p = login("parent@demo.studyroute.test", "Sandbox#2026").json()["access_token"]
ph = {"Authorization": f"Bearer {p}"}
body = {"target": {"amount_minor": 100000, "currency": "GBP"}, "purpose": "TUITION", "destination_country": "GB", "charge_code": "OUR"}
codes = [c.post(f"{BASE}/quotes", headers=ph, json=body).status_code for _ in range(40)]
rec("6 a flood of quote requests is throttled (429)", 429 in codes, f"{codes.count(201)} accepted, {codes.count(429)} throttled")

for n, ok, d in results:
    print(f"{'PASS' if ok else 'FAIL'}  {n}{'' if ok else '  -> ' + d}")
print(f"{sum(1 for _, ok, _ in results if ok)}/{len(results)} defended")
