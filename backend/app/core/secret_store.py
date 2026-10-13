"""Secret lookup. Environment first; in SANDBOX mode throw-away dev secrets are generated.

Dev secrets live in data/dev_secrets.json (gitignored) so tokens and ciphertext survive a
restart. Production mode never generates anything: missing secrets stop the app at startup.
"""

from __future__ import annotations

import base64
import json
import os
import secrets
import threading
from collections.abc import Callable, Iterable

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec

from app.core.config import Settings


class MissingSecretError(RuntimeError):
    pass


def webhook_env_name(provider_id: str, *, previous: bool = False) -> str:
    base = f"WEBHOOK_SECRET_{provider_id.upper()}"
    return f"{base}_PREVIOUS" if previous else base


def _generate_ec_pem() -> str:
    key = ec.generate_private_key(ec.SECP256R1())
    return key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    ).decode("ascii")


def _generate_aes_key() -> str:
    return base64.b64encode(secrets.token_bytes(32)).decode("ascii")


def _generate_hex_secret() -> str:
    return secrets.token_hex(32)


class SecretStore:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._lock = threading.Lock()
        self._path = settings.data_dir / "dev_secrets.json"

    @staticmethod
    def _env(name: str) -> str | None:
        value = os.environ.get(name)
        return value if value else None

    def _dev_value(self, name: str, factory: Callable[[], str]) -> str:
        with self._lock:
            store: dict[str, str] = {}
            if self._path.is_file():
                store = json.loads(self._path.read_text(encoding="utf-8"))
            if name not in store:
                store[name] = factory()
                self._path.parent.mkdir(parents=True, exist_ok=True)
                tmp = self._path.with_suffix(".tmp")
                tmp.write_text(json.dumps(store, indent=2), encoding="utf-8")
                os.replace(tmp, self._path)
            return store[name]

    def _require(self, env_name: str, factory: Callable[[], str]) -> str:
        value = self._env(env_name)
        if value:
            return value
        if not self._settings.is_sandbox:
            raise MissingSecretError(f"{env_name} is required when APP_ENV=production")
        return self._dev_value(env_name, factory)

    def jwt_private_pem(self) -> str:
        return self._require("JWT_PRIVATE_KEY_PEM", _generate_ec_pem).replace("\n", "\n")

    def jwt_public_pem(self) -> str:
        private = serialization.load_pem_private_key(self.jwt_private_pem().encode(), password=None)
        public = private.public_key()
        return public.public_bytes(
            serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo
        ).decode("ascii")

    def encryption_key(self) -> bytes:
        return base64.b64decode(self._require("DATA_ENCRYPTION_KEY", _generate_aes_key))

    def webhook_secrets(self, provider_id: str) -> list[str]:
        """Current secret first, then the optional previous secret used during rotation."""
        current = self._require(webhook_env_name(provider_id), _generate_hex_secret)
        previous = self._env(webhook_env_name(provider_id, previous=True))
        return [current, previous] if previous else [current]

    def assert_ready(self, provider_ids: Iterable[str]) -> None:
        """Fail fast at startup. Sandbox mode can always generate what is missing."""
        self.jwt_private_pem()
        self.encryption_key()
        for provider_id in provider_ids:
            self.webhook_secrets(provider_id)
