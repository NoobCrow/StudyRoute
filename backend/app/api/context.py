"""The object that holds every service. Built once at startup, stored on app.state."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.api.rate_limit import RateLimiter
from app.audit.service import AuditService
from app.core.clock import Clock
from app.core.config import Settings
from app.core.crypto import FieldCipher
from app.core.db import Database
from app.core.secret_store import SecretStore
from app.domain.auth import PasswordService, TokenService
from app.domain.config_service import ConfigService
from app.domain.documents import DocumentService
from app.domain.kyc import KycService
from app.domain.payments import PaymentService
from app.domain.quotes import QuoteService
from app.domain.recipients import RecipientService
from app.providers.registry import ProviderRegistry
from app.providers.simulator import ProviderSimulator


@dataclass
class AppContext:
    settings: Settings
    clock: Clock
    db: Database
    secrets: SecretStore
    cipher: FieldCipher
    audit: AuditService
    passwords: PasswordService
    tokens: TokenService
    limiter: RateLimiter
    providers: ProviderRegistry
    simulator: ProviderSimulator
    recipients: RecipientService
    quotes: QuoteService
    payments: PaymentService
    kyc: KycService
    documents: DocumentService
    config: ConfigService
    assistant: Any = None  # set by the container once the AI layer is built
    worker: Any = None
    sandbox: Any = None  # the sandbox service, set by the container
    reports: Any = None  # the compliance report service, set by the container
    bank: Any = None  # the sandbox bank network, set by the container
    chain: Any = None  # the sandbox chain (EVM log and replay), set by the container
    escrow: Any = None  # programmable escrow on the sandbox chain, set by the container
    reviews: Any = None  # the sandbox bank's review desk, set by the container
    login_attempts: Any = None  # failed-sign-in counter per e-mail, set by the container
