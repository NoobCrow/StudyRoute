"""Mock document uploads and the checklist tick-off. Text only; synthetic data only."""

from __future__ import annotations

import re
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.audit.service import AuditService
from app.core import errors
from app.core.clock import Clock, iso_utc
from app.core.crypto import sha256_hex
from app.core.ids import new_id
from app.domain.rbac import Actor, Perm, authorize
from app.domain.rules import Rules
from app.models import Document, Payment

MAX_CONTENT_CHARS = 20_000
_CONTROL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


def clean_filename(raw: str) -> str:
    name = raw.replace("\\", "/").rsplit("/", 1)[-1]
    name = re.sub(r"\s+", " ", _CONTROL.sub("", name)).strip()
    if not 1 <= len(name) <= 120:
        raise errors.ValidationFailed("The file name must be 1 to 120 characters.")
    return name


class DocumentService:
    def __init__(self, clock: Clock, audit: AuditService) -> None:
        self._clock = clock
        self._audit = audit

    def view(self, doc: Document) -> dict[str, Any]:
        return {
            "document_id": doc.id,
            "kind": doc.kind,
            "filename": doc.filename,
            "payment_id": doc.payment_id,
            "size_bytes": doc.size_bytes,
            "has_content": bool(doc.content_text),
            "content_preview": (doc.content_text or "")[:160],
            "sha256": doc.sha256,
            "created_at": iso_utc(doc.created_at),
            "mock": True,
        }

    def add(
        self,
        session: Session,
        actor: Actor,
        rules: Rules,
        *,
        kind: str,
        filename: str,
        content_text: str | None,
        payment_id: str | None,
    ) -> Document:
        authorize(actor, Perm.DOCUMENT_WRITE)
        if actor.owner_id is None:
            raise errors.Forbidden("Documents belong to a paying parent.")
        if kind not in rules.raw("checklist_labels"):
            raise errors.ValidationFailed("Unknown document kind. Use a checklist item key.")
        if content_text is not None and len(content_text) > MAX_CONTENT_CHARS:
            raise errors.ValidationFailed("Mock documents are limited to 20,000 characters.")
        if content_text is not None and "\x00" in content_text:
            raise errors.ValidationFailed("Only plain text mock documents are accepted.")
        if payment_id is not None:
            payment = session.get(Payment, payment_id)
            if payment is None or not actor.can_see_owner(payment.owner_id):
                raise errors.NotFound("Payment not found.")
        name = clean_filename(filename)
        body = content_text or ""
        doc = Document(
            id=new_id("doc"),
            owner_id=actor.owner_id,
            created_by=actor.user_id,
            payment_id=payment_id,
            kind=kind,
            filename=name,
            content_text=content_text or None,
            sha256=sha256_hex(body or f"{kind}:{name}"),
            size_bytes=len(body.encode("utf-8")),
            created_at=self._clock.now(),
        )
        session.add(doc)
        session.flush()
        self._audit.append(
            session,
            actor_type=actor.audit_type,
            actor_id=actor.user_id,
            action="document.added",
            payment_id=payment_id,
            input_hash=f"sha256:{doc.sha256}",
            detail=f"{kind} ({doc.size_bytes} bytes)",
        )
        return doc

    def list(self, session: Session, actor: Actor, payment_id: str | None = None) -> list[Document]:
        authorize(actor, Perm.DOCUMENT_READ)
        stmt = select(Document).order_by(Document.created_at.desc())
        if actor.owner_id is not None:
            stmt = stmt.where(Document.owner_id == actor.owner_id)
        if payment_id:
            stmt = stmt.where(Document.payment_id == payment_id)
        return list(session.execute(stmt).scalars())

    def remove(self, session: Session, actor: Actor, document_id: str) -> None:
        authorize(actor, Perm.DOCUMENT_WRITE)
        doc = session.get(Document, document_id)
        if doc is None or not actor.can_see_owner(doc.owner_id):
            raise errors.NotFound("Document not found.")
        self._audit.append(
            session,
            actor_type=actor.audit_type,
            actor_id=actor.user_id,
            action="document.removed",
            payment_id=doc.payment_id,
            detail=doc.kind,
        )
        session.delete(doc)
        session.flush()
