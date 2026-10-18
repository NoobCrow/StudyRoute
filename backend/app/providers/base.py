"""Provider adapter interface and the synthetic (mock) implementation.

Every adapter exposes get_quote, submit and status. All of them are simulations: no bank is
contacted and no money moves.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal
from enum import StrEnum
from typing import Protocol

from sqlalchemy.orm import Session

from app.core.ids import new_id
from app.engine.money import Money
from app.engine.quote import (
    ChargeCode,
    EngineParams,
    ProviderResult,
    ProviderTerms,
    compute_provider_result,
)
from app.models import ProviderLedger


class Scenario(StrEnum):
    NORMAL = "NORMAL"
    SLOW = "SLOW"
    FAIL = "FAIL"


class ProviderStatus(StrEnum):
    ACCEPTED = "ACCEPTED"
    SETTLED = "SETTLED"
    FAILED = "FAILED"


@dataclass(frozen=True)
class SubmitInstruction:
    payment_id: str
    uetr: str
    amount: Money
    charge_code: ChargeCode
    beneficiary_name: str
    beneficiary_account_masked: str
    remittance: str
    scenario: Scenario


@dataclass(frozen=True)
class SubmitAck:
    provider_reference: str
    accepted: bool
    simulated: bool
    due_at: datetime


class ProviderAdapter(Protocol):
    provider_id: str

    def get_quote(
        self,
        *,
        target: Money,
        mid_rate: Decimal,
        requested_charge_code: ChargeCode,
        params: EngineParams,
    ) -> ProviderResult: ...

    def submit(
        self, session: Session, instruction: SubmitInstruction, now: datetime
    ) -> SubmitAck: ...

    def status(self, session: Session, uetr: str) -> ProviderStatus | None: ...


@dataclass(frozen=True)
class SimulatorTiming:
    settle_delay_seconds: int
    slow_delay_seconds: int

    def delay_for(self, scenario: Scenario) -> int:
        return self.slow_delay_seconds if scenario is Scenario.SLOW else self.settle_delay_seconds


class SyntheticProvider:
    """A mock bank. Prices come from the engine; settlement is decided by the simulator."""

    def __init__(self, terms: ProviderTerms, timing: SimulatorTiming) -> None:
        self.provider_id = terms.provider_id
        self._terms = terms
        self._timing = timing

    def get_quote(
        self,
        *,
        target: Money,
        mid_rate: Decimal,
        requested_charge_code: ChargeCode,
        params: EngineParams,
    ) -> ProviderResult:
        return compute_provider_result(
            target=target,
            mid_rate=mid_rate,
            terms=self._terms,
            requested_charge_code=requested_charge_code,
            params=params,
        )

    def submit(self, session: Session, instruction: SubmitInstruction, now: datetime) -> SubmitAck:
        due_at = now + timedelta(seconds=self._timing.delay_for(instruction.scenario))
        session.add(
            ProviderLedger(
                uetr=instruction.uetr,
                provider_id=self.provider_id,
                payment_id=instruction.payment_id,
                status=ProviderStatus.ACCEPTED.value,
                scenario=instruction.scenario.value,
                submitted_at=now,
                due_at=due_at,
            )
        )
        session.flush()
        return SubmitAck(new_id("pref"), True, True, due_at)

    def status(self, session: Session, uetr: str) -> ProviderStatus | None:
        row = session.get(ProviderLedger, uetr)
        return ProviderStatus(row.status) if row else None
