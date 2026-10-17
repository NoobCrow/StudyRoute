"""Quotes, recipients, KYC, planner, checklist, rules, documents and data reset."""

from __future__ import annotations

from datetime import date
from typing import Any
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, Header, Query
from fastapi.responses import JSONResponse

from app.api.context import AppContext
from app.api.deps import get_ctx, limit_user, require
from app.api.schemas import (
    ConfigUpdateIn,
    DocumentIn,
    KycReviewIn,
    KycSubmitIn,
    QuoteIn,
    RecipientIn,
    RecipientPatchIn,
)
from app.core import errors
from app.domain import privacy
from app.domain.limits import usd_equivalent_minor
from app.domain.quotes import QuoteRequest
from app.domain.rbac import Actor, Perm
from app.domain.recipients import RecipientCreate
from app.domain.rules import load_rules
from app.domain.send_plan import build_send_plan
from app.domain.stress import parse_drops, stress_quote
from app.domain.student_guide import arrival_guide, student_budget
from app.engine import fx
from app.engine.money import CURRENCY_EXPONENTS, Money
from app.engine.planner import INDICATIVE, plan_deadline
from app.engine.rates import rate_hint, synthetic_history
from app.engine.runway import compute_runway

router = APIRouter(tags=["core"])


# --- quotes -----------------------------------------------------------------------------
@router.post("/quotes", status_code=201)
def create_quote(
    body: QuoteIn,
    actor: Actor = Depends(require(Perm.QUOTE_CREATE)),
    ctx: AppContext = Depends(get_ctx),
    _: None = Depends(limit_user("quotes")),
) -> dict[str, Any]:
    request = QuoteRequest(
        target_minor=body.target.amount_minor,
        target_currency=body.target.currency,
        purpose=body.purpose,
        destination_country=body.destination_country,
        charge_code=body.charge_code,
        recipient_id=body.recipient_id,
        due_date=body.due_date,
    )
    with ctx.db.write() as session:
        return ctx.quotes.create(session, actor, load_rules(session), request)


@router.get("/quotes/{quote_id}")
def get_quote(
    quote_id: str,
    actor: Actor = Depends(require(Perm.QUOTE_READ)),
    ctx: AppContext = Depends(get_ctx),
) -> dict[str, Any]:
    with ctx.db.read() as session:
        return ctx.quotes.get(session, actor, quote_id)


@router.get("/quotes/{quote_id}/stress")
def quote_stress(
    quote_id: str,
    drops: str | None = Query(default=None, max_length=40, pattern=r"^[0-9., ]+$"),
    provider_id: str | None = Query(default=None, max_length=40, pattern=r"^[a-z0-9_]+$"),
    actor: Actor = Depends(require(Perm.QUOTE_READ)),
    ctx: AppContext = Depends(get_ctx),
) -> dict[str, Any]:
    """Currency-drop stress test: the same quote priced again if the taka weakens. Read-only."""
    with ctx.db.read() as session:
        rules = load_rules(session)
        quote = ctx.quotes.get(session, actor, quote_id)
    return stress_quote(rules, quote, drops=parse_drops(drops), provider_id=provider_id)


@router.get("/quotes")
def list_quotes(
    limit: int = Query(default=20, ge=1, le=100),
    actor: Actor = Depends(require(Perm.QUOTE_READ)),
    ctx: AppContext = Depends(get_ctx),
) -> dict[str, Any]:
    with ctx.db.read() as session:
        return {"items": ctx.quotes.list(session, actor, limit)}


# --- recipients ---------------------------------------------------------------------------
@router.post("/recipients", status_code=201)
def create_recipient(
    body: RecipientIn,
    actor: Actor = Depends(require(Perm.RECIPIENT_CREATE)),
    ctx: AppContext = Depends(get_ctx),
) -> dict[str, Any]:
    payload = RecipientCreate(**body.model_dump())
    with ctx.db.write() as session:
        row = ctx.recipients.create(session, actor, load_rules(session), payload)
        return ctx.recipients.view(row)


@router.get("/recipients")
def list_recipients(
    actor: Actor = Depends(require(Perm.RECIPIENT_READ)), ctx: AppContext = Depends(get_ctx)
) -> dict[str, Any]:
    with ctx.db.read() as session:
        return {"items": [ctx.recipients.view(r) for r in ctx.recipients.list(session, actor)]}


@router.patch("/recipients/{recipient_id}")
def patch_recipient(
    recipient_id: str,
    body: RecipientPatchIn,
    actor: Actor = Depends(require(Perm.RECIPIENT_ALLOWLIST)),
    ctx: AppContext = Depends(get_ctx),
    x_mfa_proof: str | None = Header(default=None),
) -> dict[str, Any]:
    with ctx.db.write() as session:
        row = ctx.recipients.update(
            session,
            actor,
            load_rules(session),
            recipient_id,
            display_name=body.display_name,
            allowlisted=body.allowlisted,
            mfa_proof_raw=x_mfa_proof,
        )
        return ctx.recipients.view(row)


# --- KYC ----------------------------------------------------------------------------------
@router.get("/kyc/status")
def kyc_status(
    user_id: str | None = Query(default=None, max_length=64),
    actor: Actor = Depends(require(Perm.KYC_READ)),
    ctx: AppContext = Depends(get_ctx),
) -> dict[str, Any]:
    with ctx.db.read() as session:
        return ctx.kyc.view(session, actor, load_rules(session), user_id)


@router.post("/kyc/mock-submit")
def kyc_mock_submit(
    body: KycSubmitIn,
    actor: Actor = Depends(require(Perm.KYC_SUBMIT)),
    ctx: AppContext = Depends(get_ctx),
) -> dict[str, Any]:
    with ctx.db.write() as session:
        return ctx.kyc.mock_submit(session, actor, load_rules(session), body.documents)


@router.put("/kyc/mock-review")
def kyc_mock_review(
    body: KycReviewIn,
    actor: Actor = Depends(require(Perm.KYC_REVIEW)),
    ctx: AppContext = Depends(get_ctx),
) -> dict[str, Any]:
    with ctx.db.write() as session:
        return ctx.kyc.mock_review(session, actor, load_rules(session), body.user_id, body.status)


# --- planner, checklist, corridors ---------------------------------------------------------
@router.get("/planner/deadline")
def planner_deadline(
    due_date: date,
    country: str = Query(default="GB", pattern=r"^[A-Z]{2}$"),
    quote_id: str | None = Query(default=None, max_length=64),
    actor: Actor = Depends(require(Perm.PLANNER_READ)),
    ctx: AppContext = Depends(get_ctx),
) -> dict[str, Any]:
    now = ctx.clock.now()
    with ctx.db.read() as session:
        rules = load_rules(session)
        plan = plan_deadline(
            due_date=due_date,
            now=now,
            calendars=rules.calendars(country),
            params=rules.planner_params(),
        )
        body = plan.to_api_dict()
        extra: list[dict[str, str]] = []
        payer = ctx.kyc.view(session, actor, rules) if actor.owner_id else None
        if payer and payer["status"] != "VERIFIED":
            extra.append(
                {
                    "code": "KYC_PENDING",
                    "message": "KYC is not verified yet (simulated). "
                    "Approval stays blocked until it is.",
                }
            )
        if quote_id:
            quote = ctx.quotes.get_owned(session, actor, quote_id)
            if quote.expires_at <= now:
                extra.append(
                    {"code": "QUOTE_EXPIRED", "message": "The quote expired. Get a new one."}
                )
        body["warnings"] = body["warnings"] + extra
        body["destination_country"] = country
        return body


@router.get("/checklist")
def checklist(
    country: str = Query(default="GB", pattern=r"^[A-Z]{2}$"),
    purpose: str = Query(default="TUITION", pattern=r"^[A-Z]{3,10}$"),
    actor: Actor = Depends(require(Perm.CHECKLIST_READ)),
    ctx: AppContext = Depends(get_ctx),
) -> dict[str, Any]:
    with ctx.db.read() as session:
        body = load_rules(session).checklist(country, purpose)
        provided = {d.kind for d in ctx.documents.list(session, actor)} if actor.owner_id else set()
    for item in body["items"]:
        item["provided"] = item["key"] in provided
    return body


@router.get("/corridors")
def corridors(
    actor: Actor = Depends(require(Perm.CONFIG_READ)), ctx: AppContext = Depends(get_ctx)
) -> dict[str, Any]:
    with ctx.db.read() as session:
        rules = load_rules(session)
    items = [
        {
            "country": c.country,
            "name": c.name,
            "currency": c.currency,
            "account_scheme": c.account_scheme,
            "host_rail": c.host_rail,
            "mid_rate": f"{rules.mid_rate(c.currency)}",
            "exponent": CURRENCY_EXPONENTS[c.currency],
            "featured": c.featured,
            "restricted": c.restricted,
            "sample_amount": str(fx.sample_amount_major(rules.mid_rate(c.currency))),
        }
        for c in rules.corridors().values()
    ]
    return {"items": items, "providers": [t.provider_id for t in rules.provider_terms()]}


# --- rules configuration ------------------------------------------------------------------
@router.get("/config/rules")
def get_rules(
    actor: Actor = Depends(require(Perm.CONFIG_READ)), ctx: AppContext = Depends(get_ctx)
) -> dict[str, Any]:
    with ctx.db.read() as session:
        rules = load_rules(session).to_api()
    return {
        "rules": rules,
        "unverified_count": sum(1 for r in rules if not r["verified"]),
        "disclaimer": (
            "Indicative. Confirm with your AD bank. Rules marked not verified are placeholders."
        ),
    }


@router.put("/config/rules")
def put_rule(
    body: ConfigUpdateIn,
    actor: Actor = Depends(require(Perm.CONFIG_WRITE)),
    ctx: AppContext = Depends(get_ctx),
) -> dict[str, Any]:
    with ctx.db.write() as session:
        after = ctx.config.update(
            session,
            actor,
            key=body.key,
            value=body.value,
            source_url=body.source_url,
            verified=body.verified,
            reason=body.reason,
        )
        return after.to_api()


# --- documents ---------------------------------------------------------------------------
@router.post("/documents", status_code=201)
def add_document(
    body: DocumentIn,
    actor: Actor = Depends(require(Perm.DOCUMENT_WRITE)),
    ctx: AppContext = Depends(get_ctx),
) -> dict[str, Any]:
    with ctx.db.write() as session:
        doc = ctx.documents.add(
            session,
            actor,
            load_rules(session),
            kind=body.kind,
            filename=body.filename,
            content_text=body.content_text,
            payment_id=body.payment_id,
        )
        return ctx.documents.view(doc)


@router.get("/documents")
def list_documents(
    payment_id: str | None = Query(default=None, max_length=64),
    actor: Actor = Depends(require(Perm.DOCUMENT_READ)),
    ctx: AppContext = Depends(get_ctx),
) -> dict[str, Any]:
    with ctx.db.read() as session:
        docs = ctx.documents.list(session, actor, payment_id)
        return {"items": [ctx.documents.view(d) for d in docs]}


@router.delete("/documents/{document_id}")
def delete_document(
    document_id: str,
    actor: Actor = Depends(require(Perm.DOCUMENT_WRITE)),
    ctx: AppContext = Depends(get_ctx),
) -> dict[str, Any]:
    with ctx.db.write() as session:
        ctx.documents.remove(session, actor, document_id)
    return {"deleted": True}


# --- privacy ------------------------------------------------------------------------------
@router.post("/me/reset")
def reset_my_data(
    actor: Actor = Depends(require(Perm.DATA_RESET)), ctx: AppContext = Depends(get_ctx)
) -> JSONResponse:
    with ctx.db.write() as session:
        counts = privacy.reset_household_data(session, ctx.audit, actor)
    return JSONResponse({"reset": True, "deleted": counts})


# --- stretch: living-cost runway (F9) and synthetic rate hint (F10) -------------------------
@router.get("/planner/runway")
def runway(
    amount_minor: int = Query(gt=0, le=10**12),
    monthly_cost_minor: int = Query(gt=0, le=10**12),
    currency: str = Query(pattern=r"^[A-Z]{3}$"),
    actor: Actor = Depends(require(Perm.PLANNER_READ)),
    ctx: AppContext = Depends(get_ctx),
) -> dict[str, Any]:
    with ctx.db.read() as session:
        rules = load_rules(session)
    if currency not in rules.supported_currencies():
        raise errors.ValidationFailed(f"Unsupported currency: {currency}.")
    result = compute_runway(Money(amount_minor, currency), Money(monthly_cost_minor, currency))
    body = result.to_api_dict()
    monthly_usd = usd_equivalent_minor(rules, result.monthly_cost)
    living = rules.record("bangladesh_rules.living_expense_usd_per_month")
    body["monthly_cost_usd_equivalent"] = Money(monthly_usd, "USD").format()
    body["reference"] = {
        "label": "Indicative living-expense figure per month (secondary source)",
        "value": Money.from_major(living.value, "USD").format(),
        "verified": living.verified,
        "badge": None if living.verified else "NOT_VERIFIED",
        "note": f"Shown for comparison only. {INDICATIVE}",
    }
    return body


@router.get("/planner/send-plan")
def send_plan(
    monthly_minor: int = Query(gt=0, le=10**10),
    currency: str = Query(pattern=r"^[A-Z]{3}$"),
    months: int = Query(default=12, ge=1, le=60),
    charge_code: str = Query(default="OUR", pattern=r"^(OUR|SHA|BEN)$"),
    actor: Actor = Depends(require(Perm.PLANNER_READ)),
    ctx: AppContext = Depends(get_ctx),
) -> dict[str, Any]:
    """Smart send plan: the same living costs sent monthly, quarterly, per term or at once."""
    with ctx.db.read() as session:
        rules = load_rules(session)
    if currency not in rules.supported_currencies():
        raise errors.ValidationFailed(f"Unsupported currency: {currency}.")
    _, body = build_send_plan(
        rules, total=Money(monthly_minor * months, currency), months=months, charge_code=charge_code
    )
    return body


@router.get("/planner/student-budget")
def student_budget_route(
    budget_bdt_minor: int | None = Query(default=None, gt=0, le=10**12),
    housing: str = Query(default="shared", pattern=r"^(shared|studio)$"),
    country: str | None = Query(default=None, pattern=r"^[A-Z]{2}$"),
    actor: Actor = Depends(require(Perm.PLANNER_READ)),
    ctx: AppContext = Depends(get_ctx),
) -> dict[str, Any]:
    """Student budget: a month in each city, set against a monthly budget in taka. Read-only."""
    with ctx.db.read() as session:
        rules = load_rules(session)
    budget = Money(budget_bdt_minor, "BDT") if budget_bdt_minor is not None else None
    return student_budget(rules, budget_bdt=budget, housing=housing, country=country)


@router.get("/planner/arrival-guide")
def arrival_guide_route(
    country: str = Query(default="GB", pattern=r"^[A-Z]{2}$"),
    actor: Actor = Depends(require(Perm.PLANNER_READ)),
    ctx: AppContext = Depends(get_ctx),
) -> dict[str, Any]:
    """Arrival guide: what to do before flying and in the first weeks. Read-only."""
    with ctx.db.read() as session:
        rules = load_rules(session)
    return arrival_guide(rules, country)


@router.get("/rates/history")
def rate_history(
    currency: str = Query(default="GBP", pattern=r"^[A-Z]{3}$"),
    days: int | None = Query(default=None, ge=7, le=90),
    actor: Actor = Depends(require(Perm.PLANNER_READ)),
    ctx: AppContext = Depends(get_ctx),
) -> dict[str, Any]:
    with ctx.db.read() as session:
        rules = load_rules(session)
    if currency not in rules.supported_currencies():
        raise errors.ValidationFailed(f"Unsupported currency: {currency}.")
    today = ctx.clock.now().astimezone(ZoneInfo("Asia/Dhaka")).date()
    points = synthetic_history(
        currency, rules.mid_rate(currency), today, days or int(rules.raw("fx.history_days"))
    )
    return {
        "currency": currency,
        "source": "synthetic",
        "points": [{"date": p.day.isoformat(), "rate": str(p.rate)} for p in points],
        "hint": rate_hint(points).to_api_dict(),
        "disclaimer": "Synthetic data. Not a live feed and not a forecast.",
    }
