"""Show the AI risk model and the bank review desk working, against a running API.

    python -m app.scripts.review_demo                       # http://127.0.0.1:8000
    python -m app.scripts.review_demo --base-url http://localhost:8080

Needs the seeded demo accounts. It plays one busy afternoon for the demo family: five quick payments
to the university it already pays, then a first payment to a new university. The risk model reads
the last one as unusual (the first five are ordinary), so it waits for the bank. Then a reviewer
asks a question, the parent answers, the reviewer clears it with MFA, and the parent approves with
MFA. The five lead-in payments are cancelled afterwards so repeated runs stay under the daily cap.
Each step prints OK or FAIL; the exit code is 0 only when every check passed. Sandbox only.
"""

from __future__ import annotations

import argparse
import sys
import time
import uuid
from typing import Any

import httpx

from app.core.config import DEFAULT_DEMO_PASSWORD, DEFAULT_SANDBOX_MFA_CODE
from app.core.demo import ADMIN_EMAIL, PARENT_EMAIL

LEAD_IN = 5
SMALL, BIG = 200_000, 800_000  # GBP 2,000 five times, then GBP 8,000 (minor units)
IBAN = "GB08EXMP12345612344821"


class ReviewDemo:
    def __init__(
        self, client: httpx.Client, password: str, mfa_code: str, leave_open: bool = False
    ) -> None:
        self._leave_open = leave_open
        self._client = client
        self._password = password
        self._mfa_code = mfa_code
        self._tokens: dict[str, str] = {}
        self.failures: list[str] = []

    def _call(
        self, method: str, path: str, who: str, *, json: Any = None, mfa: str | None = None
    ) -> httpx.Response:
        headers = {"Authorization": f"Bearer {self._tokens[who]}"}
        if method != "GET":
            headers["Idempotency-Key"] = str(uuid.uuid4())
        if mfa:
            headers["X-MFA-Proof"] = mfa
        reply = self._client.request(method, f"/api/v1{path}", json=json, headers=headers)
        for _ in range(4):  # payment writes are limited to 10 a minute: wait as the server asks
            if reply.status_code != 429:
                break
            pause = min(65.0, float(reply.headers.get("retry-after", "10")) + 1)
            print(f"      (rate limit: waiting {pause:.0f} s as the server asks)")
            time.sleep(pause)
            reply = self._client.request(method, f"/api/v1{path}", json=json, headers=headers)
        return reply

    def _ok(self, ok: bool, message: str) -> bool:
        print(f"      {'OK  ' if ok else 'FAIL'} {message}")
        if not ok:
            self.failures.append(message)
        return ok

    def _proof(self, who: str, scope: str, subject: str) -> str:
        body = {"code": self._mfa_code, "scope": scope, "subject_id": subject}
        reply = self._call("POST", "/auth/mfa/verify", who, json=body)
        reply.raise_for_status()
        return str(reply.json()["mfa_proof"])

    def _pay(self, amount_minor: int, recipient_id: str) -> str:
        quote = self._call(
            "POST",
            "/quotes",
            "parent",
            json={
                "target": {"amount_minor": amount_minor, "currency": "GBP"},
                "purpose": "TUITION",
                "destination_country": "GB",
                "charge_code": "OUR",
                "due_date": None,
            },
        ).json()
        draft_reply = self._call(
            "POST",
            "/payments",
            "parent",
            json={
                "quote_id": quote["quote_id"],
                "provider_id": "prov_b",
                "recipient_id": recipient_id,
                "reference": f"DEMO-{uuid.uuid4().hex[:8]}",
            },
        )
        if draft_reply.status_code != 201:
            raise SystemExit(
                f"could not create the draft: {draft_reply.status_code} {draft_reply.text}"
            )
        pid = str(draft_reply.json()["payment_id"])
        self._call("POST", f"/payments/{pid}/request-approval", "parent").raise_for_status()
        return pid

    def _allowlist(self, recipient_id: str) -> None:
        proof = self._proof("parent", "allowlist_recipient", recipient_id)
        reply = self._call(
            "PATCH", f"/recipients/{recipient_id}", "parent", json={"allowlisted": True}, mfa=proof
        )
        reply.raise_for_status()

    def run(self) -> int:
        for who, email in (("parent", PARENT_EMAIL), ("admin", ADMIN_EMAIL)):
            reply = self._client.post(
                "/api/v1/auth/login", json={"email": email, "password": self._password}
            )
            reply.raise_for_status()
            self._tokens[who] = reply.json()["access_token"]

        print(
            "\n[1] Set up: identity verified, the university allowlisted, a second university added"
        )
        self._call(
            "PUT",
            "/kyc/mock-review",
            "admin",
            json={"user_id": "usr_demo_parent", "status": "VERIFIED"},
        ).raise_for_status()
        items = self._call("GET", "/recipients", "parent").json()["items"]
        known = next(r for r in items if r["display_name"].startswith("University of Example"))
        if not known["allowlisted"]:
            self._allowlist(known["recipient_id"])
        name = f"Visiting University {int(time.time())} (synthetic)"
        created = self._call(
            "POST",
            "/recipients",
            "parent",
            json={
                "type": "UNIVERSITY",
                "display_name": name,
                "country": "GB",
                "bic": "EXMPGB2L",
                "iban": IBAN,
            },
        )
        created.raise_for_status()
        new_id = created.json()["recipient_id"]
        self._allowlist(new_id)

        print(f"\n[2] Five quick payments of GBP {SMALL // 100:,} to the university already paid")
        lead_in = [self._pay(SMALL, known["recipient_id"]) for _ in range(LEAD_IN)]
        views = [self._call("GET", f"/payments/{p}/bank-review", "parent").json() for p in lead_in]
        self._ok(
            all(v["status"] == "CLEARED_AUTO" for v in views),
            "each took the fast lane (no bank check needed)",
        )
        self._ok(
            all(v["ai"] and v["ai"]["warning"] is False for v in views),
            "each has an AI risk score and no warning (scores "
            + ", ".join(str(v["ai"]["score"]) for v in views if v["ai"])
            + ")",
        )

        print(f"\n[3] A first payment of GBP {BIG // 100:,} to a new university")
        pid = self._pay(BIG, new_id)
        parent_view = self._call("GET", f"/payments/{pid}/bank-review", "parent").json()
        ai = parent_view["ai"] or {}
        self._ok(parent_view["status"] == "OPEN", "it waits for the bank")
        self._ok(
            ai.get("band") in ("MEDIUM", "HIGH"),
            f"AI risk score {ai.get('score')} out of 100, {str(ai.get('band', '?')).lower()} risk",
        )
        self._ok(bool(ai.get("warning")), "a warning is shown (a low score shows none)")
        self._ok(
            [f["title"] for f in ai.get("factors", [])]
            == ["Amount", "Frequency", "Timeline", "Person"],
            "the score is made of amount, frequency, timeline and person",
        )
        print(
            "      what raised the score: " + ", ".join(d["title"] for d in ai.get("drivers", []))
        )
        summary = self._call("GET", f"/payments/{pid}", "parent").json()["summary_hash"]
        blocked = self._call(
            "POST",
            f"/payments/{pid}/approve",
            "parent",
            json={"confirm_summary_hash": summary},
            mfa=self._proof("parent", "approve_payment", pid),
        )
        self._ok(
            blocked.status_code == 409 and blocked.json()["code"] == "BANK_REVIEW_PENDING",
            "the parent cannot approve until the bank clears it (BANK_REVIEW_PENDING)",
        )

        if self._leave_open:
            for p in lead_in:
                self._call("POST", f"/payments/{p}/cancel", "parent")
            print(f"\nLeft waiting for the bank: {pid}")
            return 1 if self.failures else 0

        print("\n[4] The reviewer asks a question, the parent answers, the reviewer says yes")
        queue = self._call("GET", "/bank-review/queue", "admin").json()
        self._ok(
            any(i["payment_id"] == pid for i in queue["items"]), "it is in the reviewer's queue"
        )
        ask = self._call(
            "POST",
            f"/payments/{pid}/bank-review/decision",
            "admin",
            json={
                "decision": "ASK_INFO",
                "reason_code": "DOCUMENTS_MISSING",
                "note": "Please send the fee demand note.",
            },
            mfa=self._proof("admin", "review_payment", pid),
        )
        self._ok(
            ask.status_code == 200, "the reviewer asked for the fee demand note (signed with MFA)"
        )
        reply = self._call(
            "POST",
            f"/payments/{pid}/bank-review/reply",
            "parent",
            json={"message": "Uploaded the fee demand note."},
        )
        self._ok(reply.status_code == 200, "the parent answered in a few words")
        clear = self._call(
            "POST",
            f"/payments/{pid}/bank-review/decision",
            "admin",
            json={"decision": "CLEAR"},
            mfa=self._proof("admin", "review_payment", pid),
        )
        self._ok(
            clear.status_code == 200 and clear.json()["status"] == "CLEARED",
            "the reviewer cleared it",
        )

        print("\n[5] The parent approves with a fresh MFA code")
        approved = self._call(
            "POST",
            f"/payments/{pid}/approve",
            "parent",
            json={"confirm_summary_hash": summary},
            mfa=self._proof("parent", "approve_payment", pid),
        )
        self._ok(approved.status_code == 200, "approved")

        for p in lead_in:  # tidy up so repeated runs stay under the daily cap
            self._call("POST", f"/payments/{p}/cancel", "parent")
        print(
            "\nThe AI scored all six payments and warned on one; a person decided it, "
            "and the parent authorized it with MFA."
        )
        return 1 if self.failures else 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--password", default=DEFAULT_DEMO_PASSWORD)
    parser.add_argument("--mfa-code", default=DEFAULT_SANDBOX_MFA_CODE)
    parser.add_argument(
        "--leave-open", action="store_true", help="stop while the payment waits for the bank"
    )
    args = parser.parse_args()
    with httpx.Client(base_url=args.base_url, timeout=30) as client:
        code = ReviewDemo(client, args.password, args.mfa_code, args.leave_open).run()
    print("\nOK" if code == 0 else "\nFAILED")
    return code


if __name__ == "__main__":
    sys.exit(main())
