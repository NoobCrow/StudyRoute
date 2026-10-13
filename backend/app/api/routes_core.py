"""Quotes, recipients, KYC, planner, checklist, rules, documents and data reset."""

from __future__ import annotations

from datetime import date
from typing import Any

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
from app.domain import privacy
from app.domain.quotes import QuoteRequest
from app.domain.rbac import Actor, Perm
from app.domain.recipients import RecipientCreate
from app.domain.rules import load_rules
from app.engine.planner import plan_deadline

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
    actor: Actor = Depends(require(Perm.KYC_READ)), ctx: AppContext = Depends(get_ctx)
) -> dict[str, Any]:
    with ctx.db.read() as session:
        return ctx.kyc.view(session, actor, load_rules(session))


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
