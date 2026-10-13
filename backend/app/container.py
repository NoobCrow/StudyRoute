"""Wires settings, database and services together."""

from __future__ import annotations

from app.ai.llm import build_llm_client
from app.ai.orchestrator import Orchestrator
from app.api.context import AppContext
from app.api.rate_limit import RateLimiter
from app.audit.service import AuditService
from app.core.clock import Clock, SystemClock
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
from app.domain.rules import load_rules, sync_rules_from_file
from app.providers.registry import ProviderRegistry
from app.providers.simulator import HttpWebhookDispatcher, ProviderSimulator, WebhookDispatcher
from app.worker import BackgroundWorker


def build_context(
    settings: Settings, clock: Clock | None = None, dispatcher: WebhookDispatcher | None = None
) -> AppContext:
    clock = clock or SystemClock()
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    secrets = SecretStore(settings)
    db = Database(settings.database_url)
    db.create_schema()
    audit = AuditService(clock)
    with db.write() as session:
        audit.ensure_head(session)
        sync_rules_from_file(session, settings.resolve_rules_file(), clock.now())
        provider_ids = load_rules(session).provider_ids()
    secrets.assert_ready(provider_ids)

    cipher = FieldCipher(secrets.encryption_key())
    tokens = TokenService(
        secrets.jwt_private_pem(),
        secrets.jwt_public_pem(),
        settings.jwt_issuer,
        settings.jwt_audience,
        settings.access_token_ttl_seconds,
    )
    providers = ProviderRegistry(settings)
    recipients = RecipientService(clock, audit, cipher)
    quotes = QuoteService(clock, audit, recipients)
    kyc = KycService(clock, audit)
    payments = PaymentService(clock, audit, recipients, quotes, kyc, providers)
    dispatcher = dispatcher or HttpWebhookDispatcher(settings.webhook_base_url)
    ctx = AppContext(
        settings=settings,
        clock=clock,
        db=db,
        secrets=secrets,
        cipher=cipher,
        audit=audit,
        passwords=PasswordService(
            settings.argon2_time_cost, settings.argon2_memory_kib, settings.argon2_parallelism
        ),
        tokens=tokens,
        limiter=RateLimiter(clock, settings.rate_limit_enabled),
        providers=providers,
        simulator=ProviderSimulator(db, clock, secrets, dispatcher),
        recipients=recipients,
        quotes=quotes,
        payments=payments,
        kyc=kyc,
        documents=DocumentService(clock, audit),
        config=ConfigService(clock, audit),
    )
    ctx.worker = BackgroundWorker(ctx)
    ctx.assistant = Orchestrator(ctx, build_llm_client(settings))
    return ctx
