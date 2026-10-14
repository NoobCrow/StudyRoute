"""StudyRoute sandbox API. Synthetic data only: no real money moves."""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import APIRouter, FastAPI
from starlette.middleware.cors import CORSMiddleware

from app.api import (
    routes_assistant,
    routes_audit,
    routes_auth,
    routes_bank,
    routes_core,
    routes_escrow,
    routes_payments,
    routes_sandbox,
    routes_webhooks,
)
from app.api.middleware import SecurityMiddleware, cors_kwargs
from app.container import build_context
from app.core.clock import Clock, iso_utc
from app.core.config import Settings, get_settings
from app.core.demo import demo_hints
from app.core.errors import install_error_handlers
from app.core.logging import setup_logging
from app.providers.simulator import WebhookDispatcher

VERSION = "1.0.0"
BANNER = "Sandbox - synthetic data - no real money moves"
logger = logging.getLogger("studyroute")


def create_app(
    settings: Settings | None = None,
    clock: Clock | None = None,
    dispatcher: WebhookDispatcher | None = None,
) -> FastAPI:
    setup_logging()
    settings = settings or get_settings()
    ctx = build_context(settings, clock, dispatcher)

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        if settings.simulator_enabled and ctx.worker is not None:
            ctx.worker.start()
        logger.info("StudyRoute started in %s mode (AI: %s)", settings.app_env, _ai_mode(ctx))
        yield
        if ctx.worker is not None:
            ctx.worker.stop()
        ctx.db.dispose()

    docs = settings.enable_api_docs and settings.is_sandbox
    app = FastAPI(
        title="StudyRoute sandbox API",
        version=VERSION,
        description=f"{BANNER}. Indicative guidance only. Confirm with your AD bank.",
        docs_url="/api/v1/docs" if docs else None,
        redoc_url="/api/v1/redoc" if docs else None,
        openapi_url="/api/v1/openapi.json" if docs else None,
        lifespan=lifespan,
    )
    app.state.ctx = ctx
    install_error_handlers(app)
    app.add_middleware(CORSMiddleware, **cors_kwargs(settings.cors_origin_list))
    app.add_middleware(
        SecurityMiddleware, max_body_bytes=settings.max_body_bytes, sandbox=settings.is_sandbox
    )

    api = APIRouter(prefix="/api/v1")
    for module in (
        routes_auth,
        routes_core,
        routes_payments,
        routes_audit,
        routes_webhooks,
        routes_assistant,
        routes_sandbox,
        routes_bank,
        routes_escrow,
    ):
        api.include_router(module.router)

    def health() -> dict[str, object]:
        demo = demo_hints(settings)
        body: dict[str, object] = {
            "status": "ok",
            "app": "StudyRoute",
            "version": VERSION,
            "mode": settings.app_env,
            "banner": BANNER,
            "ai_mode": _ai_mode(ctx),
            "time": iso_utc(ctx.clock.now()),
        }
        if demo is not None:
            body["demo"] = demo
        return body

    api.add_api_route("/health", health, methods=["GET"], tags=["meta"])
    app.add_api_route("/health", health, methods=["GET"], tags=["meta"])
    app.include_router(api)
    return app


def _ai_mode(ctx: object) -> str:
    assistant = getattr(ctx, "assistant", None)
    return str(getattr(assistant, "mode", "unavailable"))
