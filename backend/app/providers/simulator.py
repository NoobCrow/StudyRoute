"""Simulated provider back-office: after a submit it sends an HMAC-signed status webhook.

The simulator talks to the API exactly like a real provider would (HTTP + signature), so the
webhook verification code is exercised end to end. Everything is labelled simulated.
"""

from __future__ import annotations

import hashlib
import json
import logging
from collections.abc import Mapping
from datetime import timedelta
from typing import Protocol

import httpx
from sqlalchemy import select

from app.core.clock import Clock, iso_utc
from app.core.db import Database
from app.core.secret_store import SecretStore
from app.models import ProviderLedger
from app.providers.base import ProviderStatus, Scenario
from app.providers.webhooks import build_header

logger = logging.getLogger("studyroute.simulator")

WEBHOOK_PATH = "/api/v1/webhooks/provider"
RETRY_SECONDS = 5
MAX_ATTEMPTS = 8
BATCH = 20


class WebhookDispatcher(Protocol):
    def post(self, body: bytes, headers: Mapping[str, str]) -> int:
        """Deliver one webhook and return the HTTP status code."""
        ...


class HttpWebhookDispatcher:
    def __init__(self, base_url: str, timeout: float = 5.0) -> None:
        self._url = base_url.rstrip("/") + WEBHOOK_PATH
        self._timeout = timeout

    def post(self, body: bytes, headers: Mapping[str, str]) -> int:
        response = httpx.post(self._url, content=body, headers=dict(headers), timeout=self._timeout)
        return response.status_code


def event_id_for(uetr: str, event: str) -> str:
    """Deterministic, so a retried delivery carries the same X-Event-Id and is de-duplicated."""
    return "evt_" + hashlib.sha256(f"{uetr}:{event}".encode()).hexdigest()[:24]


class ProviderSimulator:
    def __init__(
        self, db: Database, clock: Clock, secrets: SecretStore, dispatcher: WebhookDispatcher
    ) -> None:
        self._db = db
        self._clock = clock
        self._secrets = secrets
        self._dispatcher = dispatcher

    def deliver_due(self) -> int:
        """Send every webhook whose time has come. Returns how many were delivered."""
        now = self._clock.now()
        with self._db.read() as session:
            due = (
                session.execute(
                    select(ProviderLedger)
                    .where(
                        ProviderLedger.status == ProviderStatus.ACCEPTED.value,
                        ProviderLedger.due_at <= now,
                    )
                    .order_by(ProviderLedger.due_at)
                    .limit(BATCH)
                )
                .scalars()
                .all()
            )
            jobs = [(r.uetr, r.provider_id, r.payment_id, r.scenario) for r in due]
        delivered = 0
        for uetr, provider_id, payment_id, scenario in jobs:
            outcome = self._send(uetr, provider_id, payment_id, scenario)
            self._record(uetr, outcome)
            delivered += 1 if outcome is not None else 0
        return delivered

    def _send(self, uetr: str, provider_id: str, payment_id: str, scenario: str) -> int | None:
        event = "payment.failed" if scenario == Scenario.FAIL.value else "payment.settled"
        now = self._clock.now()
        body = json.dumps(
            {
                "event": event,
                "payment_id": payment_id,
                "uetr": uetr,
                "occurred_at": iso_utc(now),
                "simulated": True,
            },
            separators=(",", ":"),
        ).encode("utf-8")
        secret = self._secrets.webhook_secrets(provider_id)[0]
        headers = {
            "Content-Type": "application/json",
            "X-Signature": build_header(secret, int(now.timestamp()), body),
            "X-Event-Id": event_id_for(uetr, event),
        }
        try:
            return self._dispatcher.post(body, headers)
        except httpx.HTTPError as exc:
            logger.warning("webhook delivery failed for %s: %s", payment_id, type(exc).__name__)
            return None

    def _record(self, uetr: str, http_status: int | None) -> None:
        now = self._clock.now()
        with self._db.write() as session:
            row = session.get(ProviderLedger, uetr)
            if row is None:
                return
            row.attempts += 1
            retryable = http_status is None or http_status >= 500 or http_status == 429
            if http_status is not None and 200 <= http_status < 300:
                row.status = (
                    ProviderStatus.FAILED.value
                    if row.scenario == Scenario.FAIL.value
                    else ProviderStatus.SETTLED.value
                )
                row.delivered_at = now
            elif retryable and row.attempts < MAX_ATTEMPTS:
                row.due_at = now + timedelta(seconds=RETRY_SECONDS * row.attempts)
            else:
                row.status = ProviderStatus.FAILED.value
                row.delivered_at = now
                logger.warning("webhook for %s rejected with status %s", uetr, http_status)
