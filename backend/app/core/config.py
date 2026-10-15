"""Runtime settings. Read from environment variables (and an optional .env file)."""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path
from typing import Literal

from dotenv import load_dotenv
from pydantic import SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

AppEnv = Literal["sandbox", "production"]

# Documented SANDBOX-ONLY constants. They are not secrets: they let a judge run the demo
# without an authenticator app. Production mode ignores them.
DEFAULT_SANDBOX_MFA_CODE = "246810"
DEFAULT_DEMO_PASSWORD = "Sandbox#2026"  # noqa: S105

_REPO_ROOT = Path(__file__).resolve().parents[3]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(extra="ignore", case_sensitive=False, env_ignore_empty=True)

    app_env: AppEnv = "sandbox"
    database_url: str = ""
    data_dir: Path = Path("data")
    rules_file: Path | None = None
    bank_network_file: Path | None = None
    cors_origins: str = "http://localhost:5173,http://localhost:8080,http://127.0.0.1:8080"

    sandbox_mfa_code: str | None = DEFAULT_SANDBOX_MFA_CODE
    seed_demo_password: str | None = None

    jwt_issuer: str = "studyroute-sandbox"
    jwt_audience: str = "studyroute-api"
    access_token_ttl_seconds: int = 900
    refresh_token_ttl_seconds: int = 7 * 24 * 3600
    argon2_time_cost: int = 2
    argon2_memory_kib: int = 19456
    argon2_parallelism: int = 1
    max_failed_logins: int = 5
    lockout_seconds: int = 900
    max_failed_mfa: int = 5
    mfa_lockout_seconds: int = 300

    max_body_bytes: int = 65_536
    rate_limit_enabled: bool = True
    enable_api_docs: bool = True
    show_demo_hints: bool = True

    simulator_enabled: bool = True
    submit_delay_seconds: int = 3
    settle_delay_seconds: int = 5
    slow_settle_delay_seconds: int = 30
    webhook_base_url: str = "http://127.0.0.1:8000"
    worker_tick_seconds: float = 1.0

    llm_provider: Literal["anthropic", "openai_compatible"] | None = None
    llm_api_key: SecretStr | None = None
    llm_model: str | None = None
    llm_base_url: str | None = None
    llm_timeout_seconds: float = 20.0
    # The small trained reader that understands what a parent typed (runs locally, no network).
    # "auto" uses it when onnxruntime and the model file are present; "off" uses the rules only.
    nlu_mode: Literal["auto", "off"] = "auto"
    # The small policy, trained with reinforcement learning, that chooses whether to ask, confirm or
    # plan. Needs the trained reader. "off" plans as soon as the amount is known.
    dialogue_mode: Literal["auto", "off"] = "auto"

    @model_validator(mode="after")
    def _finalise(self) -> Settings:
        if not self.database_url:
            self.database_url = f"sqlite:///{(self.data_dir / 'studyroute.db').as_posix()}"
        if self.app_env == "production":
            self.sandbox_mfa_code = None
        return self

    @property
    def is_sandbox(self) -> bool:
        return self.app_env == "sandbox"

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def demo_password(self) -> str:
        return self.seed_demo_password or DEFAULT_DEMO_PASSWORD

    def resolve_rules_file(self) -> Path:
        """Find config/rules.yaml: explicit setting, then RULES_FILE, then the usual places."""
        env_path = os.environ.get("RULES_FILE")
        candidates = [
            self.rules_file,
            Path(env_path) if env_path else None,
            Path(__file__).resolve().parents[2] / "config" / "rules.yaml",
            _REPO_ROOT / "config" / "rules.yaml",
        ]
        for candidate in candidates:
            if candidate is not None and candidate.is_file():
                return candidate
        raise FileNotFoundError("config/rules.yaml not found. Set RULES_FILE.")

    def resolve_bank_network_file(self) -> Path:
        """Find config/bank_network.yaml: the setting, then BANK_NETWORK_FILE, then usual places."""
        env_path = os.environ.get("BANK_NETWORK_FILE")
        candidates = [
            self.bank_network_file,
            Path(env_path) if env_path else None,
            Path(__file__).resolve().parents[2] / "config" / "bank_network.yaml",
            _REPO_ROOT / "config" / "bank_network.yaml",
        ]
        for candidate in candidates:
            if candidate is not None and candidate.is_file():
                return candidate
        raise FileNotFoundError("config/bank_network.yaml not found. Set BANK_NETWORK_FILE.")


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    load_dotenv(_REPO_ROOT / ".env", override=False)
    load_dotenv(override=False)
    return Settings()
