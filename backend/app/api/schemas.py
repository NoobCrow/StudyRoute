"""Request bodies. Strict: unknown fields are rejected, money is an integer, never a float."""

from __future__ import annotations

from datetime import date
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, SecretStr, StrictInt, StrictStr

from app.domain.constants import KycStatus


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class LoginIn(Strict):
    email: StrictStr = Field(min_length=3, max_length=254)
    password: StrictStr = Field(min_length=1, max_length=200)


class RefreshIn(Strict):
    refresh_token: StrictStr = Field(min_length=10, max_length=200)


class MfaVerifyIn(Strict):
    code: StrictStr = Field(min_length=4, max_length=12)
    scope: StrictStr = Field(max_length=32)
    subject_id: StrictStr = Field(min_length=3, max_length=64)


class MoneyIn(Strict):
    amount_minor: StrictInt = Field(gt=0, le=10**12)
    currency: StrictStr = Field(pattern=r"^[A-Z]{3}$")


class QuoteIn(Strict):
    target: MoneyIn
    purpose: StrictStr = "TUITION"
    destination_country: StrictStr = Field(pattern=r"^[A-Z]{2}$")
    charge_code: StrictStr = "OUR"
    recipient_id: StrictStr | None = Field(default=None, max_length=64)
    due_date: date | None = None


class RecipientIn(Strict):
    type: StrictStr = Field(max_length=16)
    display_name: StrictStr = Field(min_length=1, max_length=200)
    country: StrictStr = Field(pattern=r"^[A-Z]{2}$")
    bic: StrictStr = Field(min_length=1, max_length=20)
    iban: StrictStr | None = Field(default=None, max_length=60)
    account_number: StrictStr | None = Field(default=None, max_length=60)
    routing_code: StrictStr | None = Field(default=None, max_length=20)


class RecipientPatchIn(Strict):
    display_name: StrictStr | None = Field(default=None, min_length=1, max_length=200)
    allowlisted: bool | None = None


class PaymentIn(Strict):
    quote_id: StrictStr = Field(max_length=64)
    provider_id: StrictStr = Field(max_length=40)
    recipient_id: StrictStr = Field(max_length=64)
    reference: StrictStr = Field(min_length=1, max_length=140)
    due_date: date | None = None


class RequoteIn(Strict):
    quote_id: StrictStr = Field(max_length=64)
    provider_id: StrictStr = Field(max_length=40)


class ApproveIn(Strict):
    confirm_summary_hash: StrictStr = Field(min_length=10, max_length=80)


class RejectIn(Strict):
    reason: StrictStr | None = Field(default=None, max_length=200)


class KycSubmitIn(Strict):
    documents: list[StrictStr] = Field(min_length=1, max_length=20)


class KycReviewIn(Strict):
    user_id: StrictStr = Field(max_length=64)
    status: KycStatus


class ConfigUpdateIn(Strict):
    key: StrictStr = Field(min_length=3, max_length=120)
    value: Any
    source_url: StrictStr | None = Field(default=None, max_length=300)
    verified: bool = False
    reason: StrictStr = Field(min_length=3, max_length=160)


class DocumentIn(Strict):
    kind: StrictStr = Field(max_length=40)
    filename: StrictStr = Field(min_length=1, max_length=200)
    content_text: StrictStr | None = Field(default=None, max_length=20_000)
    payment_id: StrictStr | None = Field(default=None, max_length=64)


class PendingTaskIn(Strict):
    """A task the assistant asked about. The page sends it back so the person can answer in the
    next message ("GBP 10,000 by 28 October") without repeating everything."""

    kind: Literal["payment_plan", "send_plan"]
    amount_minor: StrictInt | None = Field(default=None, gt=0, le=10**10)
    currency: StrictStr | None = Field(default=None, min_length=3, max_length=3)
    due_date: date | None = None
    purpose: Literal["TUITION", "LIVING"] | None = None
    months: StrictInt | None = Field(default=None, ge=1, le=60)
    charge_code: Literal["OUR", "SHA", "BEN"] | None = None
    # Where the conversation about the task stands (see app.ai.dialogue). All optional.
    date_skipped: bool = False
    awaiting_confirmation: bool = False
    extra_amount: bool = False
    turns: StrictInt = Field(default=0, ge=0, le=20)
    asked: list[bool] = Field(
        default_factory=lambda: [False, False, False], min_length=3, max_length=3
    )
    conf_amount: float | None = Field(default=None, ge=0, le=1)
    conf_date: float | None = Field(default=None, ge=0, le=1)
    conf_months: float | None = Field(default=None, ge=0, le=1)


class CloudConnectionIn(Strict):
    provider: Literal["gemini", "groq"]
    api_key: SecretStr = Field(min_length=10, max_length=512, repr=False)
    consent: Literal[True]


class ConversationTurnIn(Strict):
    role: Literal["user", "assistant"]
    text: StrictStr = Field(min_length=1, max_length=2000)


class ChatContextIn(Strict):
    quote_id: StrictStr | None = Field(default=None, max_length=64)
    payment_id: StrictStr | None = Field(default=None, max_length=64)
    pending: PendingTaskIn | None = None
    conversation: list[ConversationTurnIn] = Field(default_factory=list, max_length=6)
    history: list[Annotated[StrictStr, Field(min_length=1, max_length=1000)]] = Field(
        default_factory=list, max_length=6
    )


class ChatIn(Strict):
    message: StrictStr = Field(min_length=1, max_length=1000)
    context: ChatContextIn = Field(default_factory=ChatContextIn)
    connection: CloudConnectionIn | None = Field(default=None, repr=False)


class ProviderEventIn(Strict):
    outcome: Literal["settle", "fail"]


class BankTransferIn(Strict):
    """A simulated transfer between two customer accounts of the sandbox bank network."""

    source: StrictStr = Field(min_length=3, max_length=64)
    destination: StrictStr = Field(min_length=3, max_length=64)
    amount: MoneyIn
    rail: StrictStr | None = Field(default=None, max_length=12)
    charge_code: Literal["OUR", "SHA", "BEN"] | None = None
    reference: StrictStr = Field(default="Sandbox transfer", min_length=1, max_length=140)


class BankStepIn(Strict):
    outcome: Literal["advance", "fail"]


class EscrowPlanIn(Strict):
    """Plan an escrow on the sandbox chain. Nothing is locked until a human confirms with MFA."""

    recipient_id: StrictStr = Field(min_length=3, max_length=64)
    purpose: Literal["TUITION", "LIVING"] = "TUITION"
    total: MoneyIn
    tranches: StrictInt = Field(default=1, ge=1, le=24)
    first_release: date
    cadence: Literal["ONCE", "MONTHLY"] = "MONTHLY"
    reference: StrictStr = Field(min_length=1, max_length=70)


class ReasonIn(Strict):
    reason: StrictStr = Field(min_length=3, max_length=120)


class ChainAdvanceIn(Strict):
    days: StrictInt = Field(ge=1, le=366)
