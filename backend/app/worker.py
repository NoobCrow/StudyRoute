"""Background worker: the "system" and "provider" sides of the sandbox.

One tick (every second by default) does four things, each in its own short transaction:
finish simulated KYC reviews, return stale quotes to DRAFT, submit approved payments after the
cancellation window, deliver due provider webhooks, and move simulated bank transfers one hop
forward. Tests call tick() directly.
"""

from __future__ import annotations

import logging
import threading

from app.api.context import AppContext
from app.core import errors
from app.domain.rules import load_rules

logger = logging.getLogger("studyroute.worker")


class BackgroundWorker:
    def __init__(self, ctx: AppContext) -> None:
        self._ctx = ctx
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def tick(self) -> dict[str, int]:
        ctx = self._ctx
        with ctx.db.write() as session:
            kyc_done = ctx.kyc.complete_due_reviews(session)
            expired = ctx.payments.expire_stale_quotes(session)
        return {
            "kyc_completed": kyc_done,
            "quotes_expired": expired,
            "payments_submitted": self._submit_due(),
            "webhooks_delivered": ctx.simulator.deliver_due(),
            "bank_steps": ctx.bank.advance_due(ctx.db),
        }

    def _submit_due(self) -> int:
        ctx = self._ctx
        with ctx.db.read() as session:
            ids = ctx.payments.due_for_submission(session, ctx.settings.submit_delay_seconds)
        submitted = 0
        for payment_id in ids:
            try:
                with ctx.db.write() as session:
                    ctx.payments.submit(session, load_rules(session), payment_id)
                submitted += 1
            except errors.ApiError as exc:
                logger.info("skipped submit of %s: %s", payment_id, exc.code)
        return submitted

    def start(self) -> None:
        if self._thread is not None:
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, name="studyroute-worker", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=5)
            self._thread = None

    def _run(self) -> None:
        interval = self._ctx.settings.worker_tick_seconds
        while not self._stop.wait(interval):
            try:
                self.tick()
            except Exception:
                logger.exception("worker tick failed")
