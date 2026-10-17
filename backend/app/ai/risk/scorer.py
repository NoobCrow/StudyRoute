"""Run the shipped risk model in plain NumPy: it reads a payment and says how unusual it looks.

The bank's review desk uses that reading to decide which payments a person looks at first, and to
tell the person why. The model never approves, clears or declines anything: a human with a fresh
MFA proof decides. The weights are JSON data checked against a manifest's SHA-256 before use; if the
file is missing, wrong or ``RISK_MODE=off``, ``load_scorer`` returns None and the desk falls back to
its plain rules (see ``bank_review.py``).

The model learned from public synthetic transactions (IBM's AML generator), not from real people
and not from this corridor, so a priority is a hint about which payment looks least like the
common ones, and the reviewer's judgement is the decision.
"""

from __future__ import annotations

import hashlib
import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.ai.risk.features import FEATURES, vectorise

logger = logging.getLogger("studyroute.ai")
MODEL_DIR = Path(__file__).resolve().parent / "model"


# The four things a score is made of, in the words of the product: how big the payment is, how often
# this household paid lately, how soon after the last payment, and who is paid (and whether this
# household has paid them before). Each is hidden in turn (set to the training average) and the drop
# in the model's output is that factor's share of the score.
FACTORS = {
    "AMOUNT": ("amount_percentile",),
    "FREQUENCY": ("sender_24h", "sender_7d", "sender_total"),
    "TIMELINE": ("hours_since_last",),
    "PERSON": ("pair_count", "pair_new", "sender_new"),
}
MIN_FACTOR_SHARE = 0.25  # in the model's own units; below this a factor is "no effect"
MAX_DRIVERS = 3


@dataclass(frozen=True)
class Priority:
    """The model's risk reading of one payment: where it stands among comparable payments."""

    percentile: int  # 0..100 among the payments in the public data: 99 means "the top 1%"
    band: str  # HIGH, MEDIUM or LOW, from cut-offs set on the tuning period
    model_id: str
    sha256: str
    population: str = ""  # "first" (a first payment to this receiver) or "repeat"
    drivers: tuple[str, ...] = ()  # which factors pushed the score up, strongest first
    hit_rate: float | None = None  # in the tuning data, the share of payments in this band flagged
    factors: tuple[tuple[str, float], ...] = ()  # every factor and its share of the score

    def to_dict(self) -> dict[str, Any]:
        return {
            "percentile": self.percentile,
            "band": self.band,
            "model_id": self.model_id,
            "sha256": self.sha256[:12],
            "population": self.population,
            "drivers": list(self.drivers),
            "hit_rate": self.hit_rate,
            "factors": [{"code": code, "share": round(share, 3)} for code, share in self.factors],
        }


class RiskScorer:
    def __init__(self, directory: Path = MODEL_DIR) -> None:
        import numpy as np

        manifest = json.loads((directory / "manifest.json").read_text(encoding="utf-8"))
        path = directory / "risk.json"
        if hashlib.sha256(path.read_bytes()).hexdigest() != manifest["files"]["risk.json"]:
            raise ValueError("risk.json does not match its recorded SHA-256")
        body = json.loads(path.read_text(encoding="utf-8"))
        self._layers = [
            (np.asarray(layer["w"], dtype="float64"), np.asarray(layer["b"], dtype="float64"))
            for layer in body["layers"]
        ]
        if self._layers[0][0].shape[0] != FEATURES or self._layers[-1][0].shape[1] != 1:
            raise ValueError("risk.json does not fit the current features")
        self._mean = np.asarray(body["mean"], dtype="float64")
        self._std = np.asarray(body["std"], dtype="float64")
        # An input that never varied in the training data was always 0 there, so the network never
        # learned what to do with it. It is held at 0 here too, instead of being blown up by a tiny
        # standard deviation.
        self._live = self._std > 1e-3
        self._tables: dict[str, list[float]] = body["quantiles"]
        self._cuts = np.asarray(body["score_quantiles"], dtype="float64")
        self._bands: dict[str, dict[str, Any]] = body["bands"]
        names = list(body["features"])
        self._groups = {
            code: [names.index(n) for n in members] for code, members in FACTORS.items()
        }
        self.manifest: dict[str, Any] = manifest
        self.model_id: str = manifest["model_id"]
        self.sha256: str = manifest["files"]["risk.json"]

    def _forward(self, x: Any) -> float:
        import numpy as np

        for index, (weights, bias) in enumerate(self._layers):
            x = x @ weights + bias
            if index < len(self._layers) - 1:
                x = np.maximum(x, 0.0)
        return float(x[0])

    def _standardised(self, facts: dict[str, Any]) -> Any:
        import numpy as np

        row = vectorise({k: np.asarray([v]) for k, v in facts.items()}, self._tables)
        z = (row[0] - self._mean) / self._std
        z[~self._live] = 0.0
        return z

    def logit(self, facts: dict[str, Any]) -> float:
        return self._forward(self._standardised(facts))

    def factors(self, facts: dict[str, Any]) -> tuple[tuple[str, float], ...]:
        """Each factor's share of the score: positive raised it, negative lowered it."""
        x = self._standardised(facts)
        full = self._forward(x)
        shares = []
        for code, columns in self._groups.items():
            hidden = x.copy()
            hidden[columns] = 0.0  # the training average, after standardising
            shares.append((code, full - self._forward(hidden)))
        return tuple(shares)

    @staticmethod
    def drivers_of(factors: tuple[tuple[str, float], ...]) -> tuple[str, ...]:
        """The factors that raised the score, strongest first (at most three)."""
        raised = sorted(
            ((share, code) for code, share in factors if share >= MIN_FACTOR_SHARE), reverse=True
        )
        return tuple(code for _, code in raised[:MAX_DRIVERS])

    def score(self, facts: dict[str, Any]) -> Priority:
        import numpy as np

        logit = self.logit(facts)
        percentile = int(np.searchsorted(self._cuts, logit, side="right") - 1)
        percentile = max(0, min(100, percentile))
        high = self._bands["HIGH"]["from_logit"]
        medium = self._bands["MEDIUM"]["from_logit"]
        band = "HIGH" if logit >= high else "MEDIUM" if logit >= medium else "LOW"
        factors = self.factors(facts)
        return Priority(
            percentile,
            band,
            self.model_id,
            self.sha256,
            "first" if int(facts["pair_count"]) == 0 else "repeat",
            self.drivers_of(factors),
            self._bands[band]["flagged_share"],
            factors,
        )


def load_scorer(mode: str = "auto") -> RiskScorer | None:
    """The shipped scorer, or None (mode off, files missing, a hash mismatch)."""
    if mode == "off":
        return None
    try:
        scorer = RiskScorer()
    except Exception as error:  # the review desk works without it
        logger.warning("risk scorer not used: %s", error)
        return None
    logger.info("risk scorer loaded: %s", scorer.model_id)
    return scorer
