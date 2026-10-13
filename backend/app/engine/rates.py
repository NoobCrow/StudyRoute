"""F10 synthetic rate history and the best-day hint. INVENTED data, never a forecast."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal
from enum import StrEnum
from typing import Any

from app.engine import fx

AMPLITUDE_PCT = Decimal("1.5")
NEUTRAL_BAND_PCT = Decimal("0.5")
INDICATIVE = "Indicative. Confirm with your AD bank."


@dataclass(frozen=True)
class RatePoint:
    day: date
    rate: Decimal


class HintKind(StrEnum):
    SEND_NOW = "SEND_NOW"
    WAIT_MAY_HELP = "WAIT_MAY_HELP"
    NEUTRAL = "NEUTRAL"


def _noise(currency: str, day: date) -> Decimal:
    """Deterministic pseudo-random value in [-1, 1] from a hash (no randomness, no I/O)."""
    digest = hashlib.sha256(f"{currency}:{day.isoformat()}".encode()).digest()
    unit = Decimal(int.from_bytes(digest[:4], "big")) / Decimal(2**32 - 1)
    return unit * 2 - 1


def synthetic_history(
    currency: str, base_rate: Decimal, today: date, days: int = 30
) -> list[RatePoint]:
    """Oldest first. Today's point is exactly the configured base rate."""
    points: list[RatePoint] = []
    for offset in range(days - 1, -1, -1):
        day = today - timedelta(days=offset)
        if offset == 0:
            rate = fx.to_rate(base_rate)
        else:
            rate = fx.to_rate(base_rate * (1 + _noise(currency, day) * AMPLITUDE_PCT / 100))
        points.append(RatePoint(day, rate))
    return points


@dataclass(frozen=True)
class RateHint:
    kind: HintKind
    today: Decimal
    average: Decimal
    gap_pct: Decimal
    days: int

    @property
    def message(self) -> str:
        gap = abs(self.gap_pct).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        if self.kind is HintKind.SEND_NOW:
            core = (
                f"Today's synthetic rate is {gap}% below its {self.days}-day average, "
                "so sending now looks better than most recent days."
            )
        elif self.kind is HintKind.WAIT_MAY_HELP:
            core = (
                f"Today's synthetic rate is {gap}% above its {self.days}-day average. "
                "Waiting might give a lower rate, or it might not."
            )
        else:
            core = f"Today's synthetic rate is close to its {self.days}-day average."
        return f"{core} This is invented data and not a forecast. {INDICATIVE}"

    def to_api_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind.value,
            "today": str(self.today),
            "average": str(self.average),
            "gap_pct": str(self.gap_pct.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)),
            "days": self.days,
            "message": self.message,
            "synthetic": True,
        }


def rate_hint(points: list[RatePoint]) -> RateHint:
    """Lower is better for the parent (fewer BDT per unit). Compare today with the earlier days."""
    today = points[-1].rate
    earlier = [p.rate for p in points[:-1]] or [today]
    average = fx.to_rate(sum(earlier, Decimal(0)) / Decimal(len(earlier)))
    gap = (today - average) / average * 100
    if gap <= -NEUTRAL_BAND_PCT:
        kind = HintKind.SEND_NOW
    elif gap >= NEUTRAL_BAND_PCT:
        kind = HintKind.WAIT_MAY_HELP
    else:
        kind = HintKind.NEUTRAL
    return RateHint(kind, today, average, gap, len(points))
