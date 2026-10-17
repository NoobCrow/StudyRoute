"""SQLAlchemy tables (blueprint section 9, plus a few supporting tables)."""

from __future__ import annotations

from datetime import date, datetime
from typing import Any

from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    CheckConstraint,
    Date,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base, UTCDateTime
from app.domain.constants import (
    BankTransferStatus,
    EscrowStatus,
    KycStatus,
    PaymentState,
    RecipientType,
    ReviewStatus,
    Role,
    sql_in,
)


class User(Base):
    __tablename__ = "users"
    __table_args__ = (
        CheckConstraint(f"role IN ({sql_in(Role)})", name="ck_users_role"),
        CheckConstraint(f"kyc_status IN ({sql_in(KycStatus)})", name="ck_users_kyc_status"),
    )

    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    email: Mapped[str] = mapped_column(String(254), unique=True, index=True)
    display_name: Mapped[str] = mapped_column(String(120))
    address: Mapped[str] = mapped_column(String(300), default="")
    role: Mapped[str] = mapped_column(String(16))
    password_hash: Mapped[str | None] = mapped_column(String(255), nullable=True)
    mfa_secret_enc: Mapped[str | None] = mapped_column(String(255), nullable=True)
    last_totp_step: Mapped[int] = mapped_column(BigInteger, default=0)
    kyc_status: Mapped[str] = mapped_column(String(20), default=KycStatus.NEEDS_DOCUMENTS.value)
    parent_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    failed_logins: Mapped[int] = mapped_column(Integer, default=0)
    locked_until: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    failed_mfa: Mapped[int] = mapped_column(Integer, default=0)
    mfa_locked_until: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime)


class KycRecord(Base):
    __tablename__ = "kyc_records"

    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    status: Mapped[str] = mapped_column(String(20))
    mock_doc_refs: Mapped[list[Any]] = mapped_column(JSON, default=list)
    missing: Mapped[list[Any]] = mapped_column(JSON, default=list)
    submitted_by: Mapped[str | None] = mapped_column(String(40), nullable=True)
    submitted_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    review_due_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)


class Recipient(Base):
    __tablename__ = "recipients"
    __table_args__ = (
        CheckConstraint(f"type IN ({sql_in(RecipientType)})", name="ck_recipients_type"),
    )

    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    owner_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    created_by: Mapped[str] = mapped_column(ForeignKey("users.id"))
    type: Mapped[str] = mapped_column(String(16))
    display_name: Mapped[str] = mapped_column(String(120))
    country: Mapped[str] = mapped_column(String(2))
    bic: Mapped[str] = mapped_column(String(11))
    account_kind: Mapped[str] = mapped_column(String(16))
    routing_code: Mapped[str | None] = mapped_column(String(16), nullable=True)
    iban_or_account_enc: Mapped[str] = mapped_column(String(512))
    account_last4: Mapped[str] = mapped_column(String(4))
    allowlisted: Mapped[bool] = mapped_column(Boolean, default=False)
    allowlisted_by: Mapped[str | None] = mapped_column(String(40), nullable=True)
    allowlisted_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime)


class Quote(Base):
    __tablename__ = "quotes"

    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    owner_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    created_by: Mapped[str] = mapped_column(ForeignKey("users.id"))
    target_amount_minor: Mapped[int] = mapped_column(BigInteger)
    target_currency: Mapped[str] = mapped_column(String(3))
    purpose: Mapped[str] = mapped_column(String(16))
    destination_country: Mapped[str] = mapped_column(String(2))
    charge_code: Mapped[str] = mapped_column(String(3))
    recipient_id: Mapped[str | None] = mapped_column(ForeignKey("recipients.id"), nullable=True)
    due_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    mid_rate: Mapped[str] = mapped_column(String(32))
    mid_rate_source: Mapped[str] = mapped_column(String(40))
    mid_rate_as_of: Mapped[datetime] = mapped_column(UTCDateTime)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime)
    expires_at: Mapped[datetime] = mapped_column(UTCDateTime)
    input_hash: Mapped[str] = mapped_column(String(80))
    results_json: Mapped[dict[str, Any]] = mapped_column(JSON)


class Payment(Base):
    __tablename__ = "payments"
    __table_args__ = (
        CheckConstraint(f"state IN ({sql_in(PaymentState)})", name="ck_payments_state"),
        Index("ix_payments_owner_created", "owner_id", "created_at"),
    )

    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    owner_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    created_by: Mapped[str] = mapped_column(ForeignKey("users.id"))
    quote_id: Mapped[str] = mapped_column(ForeignKey("quotes.id"))
    provider_id: Mapped[str] = mapped_column(String(40))
    recipient_id: Mapped[str] = mapped_column(ForeignKey("recipients.id"))
    state: Mapped[str] = mapped_column(String(20))
    reference: Mapped[str] = mapped_column(String(140))
    uetr: Mapped[str | None] = mapped_column(String(36), unique=True, nullable=True)
    due_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    latest_send_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    summary_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    summary_hash: Mapped[str | None] = mapped_column(String(80), nullable=True)
    approved_by: Mapped[str | None] = mapped_column(String(40), nullable=True)
    approved_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    submitted_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    settled_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    failure_reason: Mapped[str | None] = mapped_column(String(200), nullable=True)
    usd_equivalent_minor: Mapped[int] = mapped_column(BigInteger, default=0)
    committed_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime)
    version: Mapped[int] = mapped_column(Integer, nullable=False)

    # Optimistic locking: SQLAlchemy adds "WHERE version = :old" to every UPDATE and raises
    # StaleDataError when another transaction got there first.
    __mapper_args__ = {"version_id_col": version}


class PaymentTransition(Base):
    __tablename__ = "payment_transitions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    payment_id: Mapped[str] = mapped_column(ForeignKey("payments.id"), index=True)
    from_state: Mapped[str | None] = mapped_column(String(20), nullable=True)
    to_state: Mapped[str] = mapped_column(String(20))
    event: Mapped[str] = mapped_column(String(40))
    at: Mapped[datetime] = mapped_column(UTCDateTime)
    actor_type: Mapped[str] = mapped_column(String(10))
    actor_id: Mapped[str] = mapped_column(String(40))
    note: Mapped[str | None] = mapped_column(String(200), nullable=True)


class AuditEvent(Base):
    __tablename__ = "audit_events"

    event_id: Mapped[str] = mapped_column(String(40), primary_key=True)
    seq: Mapped[int] = mapped_column(BigInteger, unique=True, index=True)
    timestamp: Mapped[str] = mapped_column(String(32))
    actor_type: Mapped[str] = mapped_column(String(10))
    actor_id: Mapped[str] = mapped_column(String(40))
    action: Mapped[str] = mapped_column(String(48), index=True)
    payment_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    quote_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    amount_minor: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    currency: Mapped[str | None] = mapped_column(String(3), nullable=True)
    recipient_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    decision: Mapped[str | None] = mapped_column(String(12), nullable=True)
    reason_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    detail: Mapped[str | None] = mapped_column(String(240), nullable=True)
    input_hash: Mapped[str | None] = mapped_column(String(80), nullable=True)
    output_hash: Mapped[str | None] = mapped_column(String(80), nullable=True)
    model_version: Mapped[str | None] = mapped_column(String(80), nullable=True)
    prev_event_hash: Mapped[str] = mapped_column(String(64))
    this_event_hash: Mapped[str] = mapped_column(String(64))


class AuditHead(Base):
    """Single row pointing at the newest audit event. Detects truncation of the log tail."""

    __tablename__ = "audit_head"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    seq: Mapped[int] = mapped_column(BigInteger, default=0)
    hash: Mapped[str] = mapped_column(String(64))


class IdempotencyKey(Base):
    __tablename__ = "idempotency_keys"
    __table_args__ = (UniqueConstraint("user_id", "key", name="uq_idempotency_user_key"),)

    user_id: Mapped[str] = mapped_column(String(40), primary_key=True)
    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    method: Mapped[str] = mapped_column(String(8))
    path: Mapped[str] = mapped_column(String(200))
    request_hash: Mapped[str] = mapped_column(String(80))
    response_status: Mapped[int] = mapped_column(Integer)
    response_body: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime)
    expires_at: Mapped[datetime] = mapped_column(UTCDateTime, index=True)


class WebhookEvent(Base):
    __tablename__ = "webhook_events"

    event_id: Mapped[str] = mapped_column(String(80), primary_key=True)
    provider_id: Mapped[str] = mapped_column(String(40))
    received_at: Mapped[datetime] = mapped_column(UTCDateTime)
    payload_hash: Mapped[str] = mapped_column(String(80))
    processed: Mapped[bool] = mapped_column(Boolean, default=False)
    outcome: Mapped[str | None] = mapped_column(String(40), nullable=True)


class ConfigRule(Base):
    __tablename__ = "config_rules"

    key: Mapped[str] = mapped_column(String(120), primary_key=True)
    value_json: Mapped[Any] = mapped_column(JSON)
    source_url: Mapped[str | None] = mapped_column(String(300), nullable=True)
    last_checked: Mapped[str | None] = mapped_column(String(10), nullable=True)
    verified: Mapped[bool] = mapped_column(Boolean, default=False)
    kind: Mapped[str] = mapped_column(String(20), default="sandbox_design")
    note: Mapped[str | None] = mapped_column(String(400), nullable=True)
    updated_by: Mapped[str] = mapped_column(String(40), default="system")
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime)


class RefreshToken(Base):
    __tablename__ = "refresh_tokens"

    token_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    family_id: Mapped[str] = mapped_column(String(40), index=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime)
    expires_at: Mapped[datetime] = mapped_column(UTCDateTime)
    used_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    revoked_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)


class BrowserSession(Base):
    """Opaque, host-only browser session; never returned to JavaScript."""

    __tablename__ = "browser_sessions"
    token_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime)
    expires_at: Mapped[datetime] = mapped_column(UTCDateTime)
    revoked_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)


class MfaProof(Base):
    __tablename__ = "mfa_proofs"

    proof_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    scope: Mapped[str] = mapped_column(String(32))
    subject_id: Mapped[str] = mapped_column(String(64))
    issued_at: Mapped[datetime] = mapped_column(UTCDateTime)
    expires_at: Mapped[datetime] = mapped_column(UTCDateTime)
    used_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)


class Document(Base):
    __tablename__ = "documents"

    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    owner_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    created_by: Mapped[str] = mapped_column(ForeignKey("users.id"))
    payment_id: Mapped[str | None] = mapped_column(ForeignKey("payments.id"), nullable=True)
    kind: Mapped[str] = mapped_column(String(40))
    filename: Mapped[str] = mapped_column(String(120))
    content_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    sha256: Mapped[str] = mapped_column(String(64))
    size_bytes: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime)


class ProviderLedger(Base):
    """The mock provider's own record of a submitted instruction (simulation only)."""

    __tablename__ = "provider_ledger"

    uetr: Mapped[str] = mapped_column(String(36), primary_key=True)
    provider_id: Mapped[str] = mapped_column(String(40))
    payment_id: Mapped[str] = mapped_column(ForeignKey("payments.id"), index=True)
    status: Mapped[str] = mapped_column(String(12))
    scenario: Mapped[str] = mapped_column(String(12), default="NORMAL")
    submitted_at: Mapped[datetime] = mapped_column(UTCDateTime)
    due_at: Mapped[datetime] = mapped_column(UTCDateTime)
    delivered_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    attempts: Mapped[int] = mapped_column(Integer, default=0)


class BankAccount(Base):
    """A ledger account in the sandbox bank network (customer or bank-internal). Synthetic."""

    __tablename__ = "bank_accounts"
    __table_args__ = (
        UniqueConstraint(
            "bank_code", "kind", "currency", "counterparty", "number", name="uq_bank_account"
        ),
        CheckConstraint("allow_negative = 1 OR balance_minor >= 0", name="ck_bank_account_balance"),
    )

    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    bank_code: Mapped[str] = mapped_column(String(16), index=True)
    kind: Mapped[str] = mapped_column(String(12))
    currency: Mapped[str] = mapped_column(String(3))
    counterparty: Mapped[str] = mapped_column(String(16), default="")
    number: Mapped[str] = mapped_column(String(40), default="", index=True)
    holder_name: Mapped[str] = mapped_column(String(120), default="")
    label: Mapped[str] = mapped_column(String(80), default="")
    owner_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"), nullable=True, index=True)
    balance_minor: Mapped[int] = mapped_column(BigInteger, default=0)
    allow_negative: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime)


class BankTransfer(Base):
    """One simulated transfer between two customer accounts, national or international."""

    __tablename__ = "bank_transfers"
    __table_args__ = (
        CheckConstraint(
            f"status IN ({sql_in(BankTransferStatus)})", name="ck_bank_transfers_status"
        ),
        Index("ix_bank_transfers_owner_created", "owner_id", "created_at"),
        Index("ix_bank_transfers_due", "status", "next_step_at"),
    )

    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    owner_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    created_by: Mapped[str] = mapped_column(ForeignKey("users.id"))
    kind: Mapped[str] = mapped_column(String(14))
    rail: Mapped[str] = mapped_column(String(12))
    status: Mapped[str] = mapped_column(String(24))
    source_account_id: Mapped[str] = mapped_column(ForeignKey("bank_accounts.id"))
    destination_account_id: Mapped[str] = mapped_column(ForeignKey("bank_accounts.id"))
    debit_minor: Mapped[int] = mapped_column(BigInteger)
    debit_currency: Mapped[str] = mapped_column(String(3))
    credit_minor: Mapped[int] = mapped_column(BigInteger)
    credit_currency: Mapped[str] = mapped_column(String(3))
    fee_minor: Mapped[int] = mapped_column(BigInteger, default=0)
    reference: Mapped[str] = mapped_column(String(140))
    uetr: Mapped[str | None] = mapped_column(String(36), nullable=True, unique=True)
    scenario: Mapped[str] = mapped_column(String(12), default="NORMAL")
    plan_json: Mapped[dict[str, Any]] = mapped_column(JSON)
    plan_hash: Mapped[str] = mapped_column(String(80))
    next_step: Mapped[int] = mapped_column(Integer, default=0)
    next_step_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    failure_reason: Mapped[str | None] = mapped_column(String(200), nullable=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime)
    confirmed_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    settled_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime)
    version: Mapped[int] = mapped_column(Integer, nullable=False)

    __mapper_args__ = {"version_id_col": version}


class LedgerJournal(Base):
    """One balanced posting. Append-only: a mistake is corrected by a reversing journal."""

    __tablename__ = "ledger_journals"

    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    transfer_id: Mapped[str | None] = mapped_column(
        ForeignKey("bank_transfers.id"), nullable=True, index=True
    )
    seq: Mapped[int] = mapped_column(Integer, default=0)
    kind: Mapped[str] = mapped_column(String(10))
    stage: Mapped[str] = mapped_column(String(24), default="")
    memo: Mapped[str] = mapped_column(String(160))
    posted_at: Mapped[datetime] = mapped_column(UTCDateTime)


class LedgerEntry(Base):
    """One line of a journal. Append-only."""

    __tablename__ = "ledger_entries"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    journal_id: Mapped[str] = mapped_column(ForeignKey("ledger_journals.id"), index=True)
    account_id: Mapped[str] = mapped_column(ForeignKey("bank_accounts.id"), index=True)
    side: Mapped[str] = mapped_column(String(6))
    amount_minor: Mapped[int] = mapped_column(BigInteger)
    currency: Mapped[str] = mapped_column(String(3))
    balance_after_minor: Mapped[int] = mapped_column(BigInteger)


class BankTransferEvent(Base):
    """The hop-by-hop history of a transfer, including the simulated message that travelled."""

    __tablename__ = "bank_transfer_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    transfer_id: Mapped[str] = mapped_column(ForeignKey("bank_transfers.id"), index=True)
    at: Mapped[datetime] = mapped_column(UTCDateTime)
    stage: Mapped[str] = mapped_column(String(24))
    bank_code: Mapped[str] = mapped_column(String(16))
    event: Mapped[str] = mapped_column(String(32))
    note: Mapped[str] = mapped_column(String(240), default="")
    message_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)


class Escrow(Base):
    """A planned or live sandbox escrow. The tranche states themselves live on the chain."""

    __tablename__ = "escrows"
    __table_args__ = (
        CheckConstraint(f"status IN ({sql_in(EscrowStatus)})", name="ck_escrows_status"),
        Index("ix_escrows_owner_created", "owner_id", "created_at"),
    )

    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    owner_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    created_by: Mapped[str] = mapped_column(ForeignKey("users.id"))
    recipient_id: Mapped[str] = mapped_column(ForeignKey("recipients.id"))
    purpose: Mapped[str] = mapped_column(String(10))
    currency: Mapped[str] = mapped_column(String(3))
    total_minor: Mapped[int] = mapped_column(BigInteger)
    cadence: Mapped[str] = mapped_column(String(8))
    reference: Mapped[str] = mapped_column(String(140))
    plan_json: Mapped[list[dict[str, Any]]] = mapped_column(JSON)
    plan_hash: Mapped[str] = mapped_column(String(80))
    status: Mapped[str] = mapped_column(String(24))
    chain_escrow_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime)
    confirmed_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime)
    version: Mapped[int] = mapped_column(Integer, nullable=False)

    __mapper_args__ = {"version_id_col": version}


class ChainLog(Base):
    """Everything that happened on the sandbox chain, in order. Append-only and hash-chained:
    each row's hash covers the one before it, and replaying the rows rebuilds the chain exactly."""

    __tablename__ = "chain_log"

    seq: Mapped[int] = mapped_column(Integer, primary_key=True)
    kind: Mapped[str] = mapped_column(String(8))  # DEPLOY, CALL or TIME
    contract: Mapped[str] = mapped_column(String(40))  # a label such as "escrow" or "token:GBP"
    function: Mapped[str | None] = mapped_column(String(40), nullable=True)  # DEPLOY: the artifact
    caller: Mapped[str] = mapped_column(String(80))  # the wallet label that sent it
    args_json: Mapped[list[Any]] = mapped_column(JSON)
    at: Mapped[int] = mapped_column(BigInteger)  # chain time, in epoch seconds
    ref: Mapped[str | None] = mapped_column(String(64), nullable=True)
    actor_id: Mapped[str] = mapped_column(String(40))
    prev_hash: Mapped[str] = mapped_column(String(64))
    tx_hash: Mapped[str] = mapped_column(String(64), unique=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime)


class SavedAIConnection(Base):
    """One encrypted provider credential per actual signed-in user, not household."""

    __tablename__ = "saved_ai_connections"
    __table_args__ = (
        CheckConstraint("provider IN ('gemini', 'groq')", name="ck_ai_connection_provider"),
    )
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), primary_key=True)
    provider: Mapped[str] = mapped_column(String(16))
    model: Mapped[str] = mapped_column(String(128))
    api_key_enc: Mapped[str] = mapped_column(Text)
    verified: Mapped[bool] = mapped_column(Boolean, default=False)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime)


class BankReview(Base):
    """One bank-side review per payment (simulated). The reviewer decides; nothing here decides."""

    __tablename__ = "bank_reviews"
    __table_args__ = (
        CheckConstraint(f"status IN ({sql_in(ReviewStatus)})", name="ck_bank_reviews_status"),
        Index("ix_bank_reviews_status_due", "status", "due_at"),
    )

    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    payment_id: Mapped[str] = mapped_column(ForeignKey("payments.id"), unique=True)
    owner_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    status: Mapped[str] = mapped_column(String(16))
    signals_json: Mapped[dict[str, Any]] = mapped_column(JSON)
    priority_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    opened_at: Mapped[datetime] = mapped_column(UTCDateTime)
    due_at: Mapped[datetime] = mapped_column(UTCDateTime)
    decided_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    decided_by: Mapped[str | None] = mapped_column(String(40), nullable=True)
    reason_code: Mapped[str | None] = mapped_column(String(32), nullable=True)
    reviewer_note: Mapped[str | None] = mapped_column(String(500), nullable=True)
    parent_reply: Mapped[str | None] = mapped_column(Text, nullable=True)  # sealed (AES-GCM)
    reminders: Mapped[int] = mapped_column(Integer, default=0)
    last_reminder_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime)
