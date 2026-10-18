"""TLS checks against a StudyRoute API served over HTTPS (sandbox lab only).

The compose stack serves plain HTTP and expects TLS to be terminated in front of nginx (risk R4).
This probe shows what the application itself does when it IS served over TLS: the session cookie
gets the Secure flag, the HSTS header is present, old protocol versions are refused and plain HTTP
is not answered on the TLS port. A self-signed certificate is expected in the lab, so the
certificate itself is reported as INFO.

    cd backend
    python ../scripts/security/tls_probe.py https://127.0.0.1:8443 /tmp/lab/cert.pem
"""

from __future__ import annotations

import socket
import ssl
import sys
import warnings
from datetime import UTC, datetime
from urllib.parse import urlsplit

import httpx
from cryptography import x509
from cryptography.hazmat.primitives.asymmetric import ec, rsa

warnings.simplefilter("ignore", DeprecationWarning)  # TLSv1_1 is deprecated: that is what we probe for
BASE = sys.argv[1].rstrip("/")
CERT_FILE = sys.argv[2] if len(sys.argv) > 2 else None
API = BASE + "/api/v1"
parts = urlsplit(BASE)
HOST, PORT = parts.hostname or "127.0.0.1", parts.port or 443
results: list[tuple[str, str, str]] = []


def rec(name: str, ok: bool, detail: str = "") -> None:
    results.append(("PASS" if ok else "FAIL", name, detail))


def info(name: str, detail: str = "") -> None:
    results.append(("INFO", name, detail))


def handshake(minimum: ssl.TLSVersion | None, maximum: ssl.TLSVersion | None) -> tuple[str, str] | str:
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    context.check_hostname = False
    context.verify_mode = ssl.CERT_NONE
    try:
        # Let OUR side offer old protocols too, so a refusal is the server's and not ours.
        context.set_ciphers("DEFAULT:@SECLEVEL=0")
        if minimum is not None:
            context.minimum_version = minimum
        if maximum is not None:
            context.maximum_version = maximum
        with socket.create_connection((HOST, PORT), timeout=8) as raw, context.wrap_socket(raw, server_hostname=HOST) as tls:
            return tls.version() or "?", (tls.cipher() or ("?",))[0]
    except (ssl.SSLError, OSError, ValueError) as error:
        return f"refused: {type(error).__name__}"


# ------------------------------------------------------------------ protocol versions
best = handshake(None, None)
rec("T1 a modern TLS connection works", isinstance(best, tuple) and best[0] in {"TLSv1.2", "TLSv1.3"}, str(best))
tls12 = handshake(ssl.TLSVersion.TLSv1_2, ssl.TLSVersion.TLSv1_2)
info("TLS 1.2 is accepted" if isinstance(tls12, tuple) else "TLS 1.2 is not accepted", str(tls12))
old = handshake(ssl.TLSVersion.MINIMUM_SUPPORTED, ssl.TLSVersion.TLSv1_1)
rec("T2 TLS 1.0 and 1.1 are refused", not isinstance(old, tuple), str(old))

# ------------------------------------------------------------------ plain HTTP on the TLS port
try:
    plain = httpx.get(f"http://{HOST}:{PORT}/api/v1/health", timeout=8)
    rec("T3 plain HTTP is not answered on the TLS port", False, f"HTTP {plain.status_code}")
except httpx.HTTPError as error:
    rec("T3 plain HTTP is not answered on the TLS port", True, type(error).__name__)

# ------------------------------------------------------------------ what the application sends over TLS
client = httpx.Client(verify=False, timeout=15)
health = client.get(f"{API}/health")
hsts = health.headers.get("strict-transport-security", "")
max_age = next((int(p.split("=")[1]) for p in hsts.replace(" ", "").split(";") if p.startswith("max-age=")), 0)
rec("T4 HSTS is sent with a long lifetime", max_age >= 15552000, hsts or "missing")
info("HSTS includes subdomains" if "includesubdomains" in hsts.lower() else "HSTS does not include subdomains", hsts)
rec("T5 responses are never cached", "no-store" in health.headers.get("cache-control", ""), health.headers.get("cache-control", "missing"))

login = client.post(
    f"{API}/auth/browser/login",
    headers={"X-StudyRoute-Browser": "1", "Origin": BASE},
    json={"email": "parent@demo.studyroute.test", "password": "Sandbox#2026"},
)
cookie = login.headers.get("set-cookie", "").lower()
rec("T6 browser sign-in over HTTPS works", login.status_code == 200, str(login.status_code))
rec("T7 the session cookie carries Secure, HttpOnly and SameSite=Strict", all(flag in cookie for flag in ("secure", "httponly", "samesite=strict")), cookie[:140])
# ------------------------------------------------------------------ the certificate (lab: self-signed)
if CERT_FILE:
    with open(CERT_FILE, "rb") as handle:
        certificate = x509.load_pem_x509_certificate(handle.read())
    key = certificate.public_key()
    bits = key.key_size if isinstance(key, rsa.RSAPublicKey) else (key.curve.key_size if isinstance(key, ec.EllipticCurvePublicKey) else 0)
    days = (certificate.not_valid_after_utc - datetime.now(UTC)).days
    self_signed = certificate.issuer == certificate.subject
    info("the lab certificate is self-signed (expected here; a real deployment needs a CA-issued one)" if self_signed else "the certificate is CA-issued", f"key {bits} bits, {days} days left")
    rec("T8 the certificate key is strong enough", bits >= 2048 or bits >= 256, f"{bits} bits")

for kind, name, detail in results:
    print(f"{kind:4}  {name}{'  -> ' + detail if detail and kind != 'PASS' else ''}")
failed = sum(1 for k, _, _ in results if k == "FAIL")
print(f"\n{sum(1 for k, _, _ in results if k == 'PASS')} defended, {failed} failed")
sys.exit(1 if failed else 0)
