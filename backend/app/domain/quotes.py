"""Quotes: ask every provider, rank by true total cost, store the result (blueprint 6, 8.3)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.audit.service import AuditService
from app.core import errors
from app.core.clock import Clock, iso_utc
from app.core.crypto import hash_object
from app.core.ids import new_id
from app.domain.constants import Purpose
from app.domain.rbac import Actor, Perm, authorize
from app.domain.recipients import RecipientService
from app.domain.rules import Rules
from app.engine.money import Money
from app.engine.quote import ChargeCode, build_quote
from app.models import Quote
from app.providers.rates import synthetic_mid_rate

MAX_AMOUNT_MINOR = 10**12
DISCLAIMER = "Sandbox. Synthetic rates and fees. Indicative guidance only."


@dataclass(frozen=True)
class QuoteRequest:
    target_minor: int
    target_currency: str
    purpose: str
    destination_country: str
    charge_code: str
    recipient_id: str | None = None
    due_date: date | None = None


class QuoteService:
    def __init__(self, clock: Clock, audit: AuditService, recipients: RecipientService) -> None:
        self._clock = clock
        self._audit = audit
        self._recipients = recipients

    def create(
        self, session: Session, actor: Actor, rules: Rules, req: QuoteRequest
    ) -> dict[str, Any]:
        authorize(actor, Perm.QUOTE_CREATE)
        if actor.owner_id is None:
            raise errors.Forbidden("Quotes belong to a paying parent.")
        corridor = rules.corridor(req.destination_country)
        if req.target_currency not in rules.supported_currencies():
            raise errors.ValidationFailed(f"Unsupported currency: {req.target_currency}.")
        if req.target_currency != corridor.currency:
            raise errors.ValidationFailed(
                f"Payments to {corridor.name} are made in {corridor.currency}."
            )
        if not 0 < req.target_minor <= MAX_AMOUNT_MINOR:
            raise errors.ValidationFailed("The amount must be greater than zero.")
        if req.purpose not in {p.value for p in Purpose}:
            raise errors.ValidationFailed("Purpose must be TUITION or LIVING.")
        try:
            charge = ChargeCode(req.charge_code)
        except ValueError as exc:
            raise errors.ValidationFailed("Charge code must be OUR, SHA or BEN.") from exc
        if req.recipient_id:
            recipient = self._recipients.get_owned(session, actor, req.recipient_id)
            if recipient.country != corridor.country:
                raise errors.ValidationFailed("The recipient is in a different country.")
        now = self._clock.now()
        if req.due_date and not date(2000, 1, 1) < req.due_date < now.date() + timedelta(days=800):
            raise errors.ValidationFailed("The due date is out of range.")

        target = Money(req.target_minor, req.target_currency)
        quote = build_quote(
            target=target,
            purpose=req.purpose,
            destination_country=corridor.country,
            charge_code=charge,
            mid_rate=synthetic_mid_rate(rules, target.currency, now),
            providers=rules.provider_terms(),
            params=rules.engine_params(),
            now=now,
        )
        results = [r.to_api_dict() for r in quote.results]
        row = Quote(
            id=new_id("qte"),
            owner_id=actor.owner_id,
            created_by=actor.user_id,
            target_amount_minor=target.amount_minor,
            target_currency=target.currency,
            purpose=req.purpose,
            destination_country=corridor.country,
            charge_code=charge.value,
            recipient_id=req.recipient_id,
            due_date=req.due_date,
            mid_rate=str(quote.mid_rate.value),
            mid_rate_source=quote.mid_rate.source,
            mid_rate_as_of=quote.mid_rate.as_of,
            created_at=quote.created_at,
            expires_at=quote.expires_at,
            input_hash=quote.input_hash,
            results_json={"results": results},
        )
        session.add(row)
        session.flush()
        self._audit.append(
            session,
            actor_type=actor.audit_type,
            actor_id=actor.user_id,
            action="quote.created",
            quote_id=row.id,
            amount_minor=target.amount_minor,
            currency=target.currency,
            recipient_id=req.recipient_id,
            input_hash=quote.input_hash,
            output_hash=hash_object(results),
        )
        return self.view(row, now)

    def get_owned(self, session: Session, actor: Actor, quote_id: str) -> Quote:
        row = session.get(Quote, quote_id)
        if row is None or not actor.can_see_owner(row.owner_id):
            raise errors.NotFound("Quote not found.")
        return row

    def get(self, session: Session, actor: Actor, quote_id: str) -> dict[str, Any]:
        authorize(actor, Perm.QUOTE_READ)
        return self.view(self.get_owned(session, actor, quote_id), self._clock.now())

    def list(self, session: Session, actor: Actor, limit: int = 20) -> list[dict[str, Any]]:
        authorize(actor, Perm.QUOTE_READ)
        stmt = select(Quote).order_by(Quote.created_at.desc()).limit(limit)
        if actor.owner_id is not None:
            stmt = stmt.where(Quote.owner_id == actor.owner_id)
        now = self._clock.now()
        return [self.view(row, now) for row in session.execute(stmt).scalars()]

    @staticmethod
    def is_expired(row: Quote, now: datetime) -> bool:
        return now >= row.expires_at

    def view(self, row: Quote, now: datetime) -> dict[str, Any]:
        target = Money(row.target_amount_minor, row.target_currency)
        return {
            "quote_id": row.id,
            "created_at": iso_utc(row.created_at),
            "expires_at": iso_utc(row.expires_at),
            "status": "EXPIRED" if self.is_expired(row, now) else "ACTIVE",
            "seconds_left": max(0, int((row.expires_at - now).total_seconds())),
            "target": target.to_dict(),
            "purpose": row.purpose,
            "destination_country": row.destination_country,
            "charge_code": row.charge_code,
            "due_date": row.due_date.isoformat() if row.due_date else None,
            "recipient_id": row.recipient_id,
            "mid_rate": {
                "value": row.mid_rate,
                "source": row.mid_rate_source,
                "as_of": iso_utc(row.mid_rate_as_of),
                "display": f"BDT {row.mid_rate} per 1 {row.target_currency} (synthetic)",
            },
            "results": row.results_json["results"],
            "input_hash": row.input_hash,
            "synthetic": True,
            "disclaimer": DISCLAIMER,
        }
