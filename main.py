"""Botkeep GitHub entrypoint: Python dependencies only, prebuilt frontend committed."""

from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "backend"))


def configure() -> int:
    from dotenv import load_dotenv

    load_dotenv(ROOT / ".env", override=False)
    try:
        port = int(os.environ.get("SERVER_PORT") or os.environ.get("PORT") or "8000")
    except ValueError as exc:
        raise RuntimeError("SERVER_PORT must be an integer") from exc
    if not 1 <= port <= 65535:
        raise RuntimeError("SERVER_PORT must be between 1 and 65535")
    defaults = {
        "ASSISTANT_CLOUD_ENABLED": "false",
        "DATA_DIR": str(ROOT / "data"),
        "WEBHOOK_BASE_URL": f"http://127.0.0.1:{port}",
        "RULES_FILE": str(ROOT / "config" / "rules.yaml"),
        "BANK_NETWORK_FILE": str(ROOT / "config" / "bank_network.yaml"),
    }
    for name, value in defaults.items():
        if not os.environ.get(name):
            os.environ[name] = value
    os.chdir(ROOT)
    return port


def create_app():
    """The full-model deployment must not silently start with local models disabled."""
    from app.hosting import create_app as hosted_app

    app = hosted_app()
    ctx = app.state.ctx
    missing = []
    if ctx.assistant._reader is None:
        missing.append("reader")
    if ctx.assistant._policy is None:
        missing.append("dialogue policy")
    if ctx.reviews._scorer is None:
        missing.append("risk scorer")
    settings = ctx.settings
    if (
        not settings.assistant_cloud_enabled
        and not settings.llm_provider
        and ctx.assistant._llm.__class__.__name__ != "LocalExplainerLLM"
    ):
        missing.append("local explainer")
    if missing:
        ctx.db.dispose()
        raise RuntimeError(
            "Required local models did not load: "
            + ", ".join(missing)
            + ". Install original requirements and set NLU_MODE, DIALOGUE_MODE, "
            "EXPLAINER_MODE and RISK_MODE to auto."
        )
    return app


if __name__ == "__main__":
    port = configure()
    from model_bootstrap import ensure_models

    ensure_models(ROOT)
    import uvicorn

    # PUBLIC_ORIGIN preserves HTTPS cookie security behind the managed TLS edge.
    # Do not trust arbitrary client-supplied proxy headers.
    uvicorn.run(
        "main:create_app",
        factory=True,
        host="0.0.0.0",
        port=port,
        workers=1,
        proxy_headers=False,
    )
