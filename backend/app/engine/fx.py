"""Exchange-rate maths. Convention: every rate is BDT per 1 unit of foreign currency."""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal, localcontext

from app.engine.money import InvalidAmount, exponent

RATE_PLACES = 6
_RATE_QUANTUM = Decimal(1).scaleb(-RATE_PLACES)
_PCT_QUANTUM = Decimal("0.01")
_PRECISION = 60
BDT = "BDT"
SAMPLE_BDT = Decimal(1_600_000)


def to_rate(value: Decimal | str | int) -> Decimal:
    """Validate and quantise a rate to six decimal places (half-up)."""
    if isinstance(value, bool | float):
        raise TypeError("rates must be Decimal, str or int, never float")
    rate = Decimal(value)
    if rate <= 0:
        raise InvalidAmount("Rates must be positive.")
    return rate.quantize(_RATE_QUANTUM, rounding=ROUND_HALF_UP)


def apply_margin(mid_rate: Decimal, margin_pct: Decimal) -> Decimal:
    """Provider selling rate = mid * (1 + margin%), kept to six decimals."""
    with localcontext() as ctx:
        ctx.prec = _PRECISION
        return to_rate(mid_rate * (Decimal(1) + margin_pct / Decimal(100)))


def margin_percent(provider_rate: Decimal, mid_rate: Decimal) -> Decimal:
    with localcontext() as ctx:
        ctx.prec = _PRECISION
        return (provider_rate - mid_rate) / mid_rate * Decimal(100)


def foreign_to_bdt_minor(foreign_minor: int, foreign_currency: str, rate: Decimal) -> Decimal:
    """Exact (unrounded) BDT minor units for an amount of foreign minor units at `rate`."""
    with localcontext() as ctx:
        ctx.prec = _PRECISION
        scale = Decimal(10) ** (exponent(BDT) - exponent(foreign_currency))
        return Decimal(foreign_minor) * rate * scale


def bdt_to_foreign_minor(bdt_minor: int, foreign_currency: str, rate: Decimal) -> Decimal:
    """Exact (unrounded) foreign minor units for an amount of BDT minor units at `rate`."""
    with localcontext() as ctx:
        ctx.prec = _PRECISION
        scale = Decimal(10) ** (exponent(foreign_currency) - exponent(BDT))
        return Decimal(bdt_minor) / rate * scale


def pct_display(value: Decimal) -> str:
    """Two decimal places, half-up, as a plain string such as 1.58."""
    return str(value.quantize(_PCT_QUANTUM, rounding=ROUND_HALF_UP))


def sample_amount_major(mid_rate: Decimal) -> int:
    """A round amount, in whole units, worth about BDT 1,600,000. It is only a form default.

    One significant figure, never below 1, so a country whose money is worth very little
    (or a lot) per unit still starts with a sensible number instead of a fixed 10,000.
    """
    with localcontext() as ctx:
        ctx.prec = _PRECISION
        raw = SAMPLE_BDT / to_rate(mid_rate)
        magnitude = Decimal(10) ** (raw.adjusted())
        rounded = (raw / magnitude).quantize(Decimal(1), rounding=ROUND_HALF_UP) * magnitude
        return max(1, int(rounded))
