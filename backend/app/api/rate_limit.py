"""In-memory sliding-window rate limiter (blueprint 8.7)."""

from __future__ import annotations

import math
import threading
from collections import deque

from app.core import errors
from app.core.clock import Clock

# group -> (limit per minute, what the limit is keyed on)
LIMITS: dict[str, tuple[int, str]] = {
    "auth": (10, "ip"),
    "browser_restore": (60, "ip"),
    "browser_logout": (10, "ip"),
    "quotes": (30, "user"),
    "payment_writes": (10, "user"),
    "bank_writes": (20, "user"),
    "chat": (20, "user"),
    "webhooks": (120, "provider"),
    "webhook_failures": (30, "ip"),
}
_PURGE_AT = 5000


class RateLimiter:
    def __init__(self, clock: Clock, enabled: bool = True) -> None:
        self._clock = clock
        self._enabled = enabled
        self._hits: dict[tuple[str, str], deque[float]] = {}
        self._lock = threading.Lock()

    def check(self, group: str, key: str, window_seconds: int = 60) -> None:
        """Count one request. Raises RateLimited (HTTP 429, Retry-After) when over the limit."""
        if not self._enabled:
            return
        limit, _ = LIMITS[group]
        now = self._clock.now().timestamp()
        with self._lock:
            hits = self._hits.setdefault((group, key), deque())
            while hits and hits[0] <= now - window_seconds:
                hits.popleft()
            if len(hits) >= limit:
                wait = max(1, math.ceil(hits[0] + window_seconds - now))
                raise errors.RateLimited(
                    "Too many requests. Slow down and retry.", headers={"Retry-After": str(wait)}
                )
            hits.append(now)
            if len(self._hits) > _PURGE_AT:
                self._purge(now - window_seconds)

    def _purge(self, oldest: float) -> None:
        for key in [k for k, v in self._hits.items() if not v or v[-1] <= oldest]:
            del self._hits[key]
