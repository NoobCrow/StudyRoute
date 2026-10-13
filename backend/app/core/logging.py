"""Logging with redaction. Nothing sensitive may reach a log line, even by accident.

Redaction is installed as a LogRecord factory, so it applies to every logger in the process
(including uvicorn and SQLAlchemy) and to formatted tracebacks.
"""

from __future__ import annotations

import contextvars
import logging
import re
import traceback
from re import Pattern

request_id_var: contextvars.ContextVar[str] = contextvars.ContextVar("request_id", default="-")

_JWT = re.compile(r"eyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}")
_BEARER = re.compile(r"(?i)\bbearer\s+[A-Za-z0-9._~+/=-]{8,}")
_KEY_VALUE = re.compile(
    r"(?i)\b(password|passwd|secret|api[_-]?key|authorization|x-mfa-proof|mfa_proof"
    r"|refresh_token|access_token|x-signature)\b(\s*[=:]\s*)(\"[^\"]*\"|'[^']*'|\S+)"
)
_EMAIL = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)+")
_IBAN = re.compile(r"\b[A-Z]{2}\d{2}(?: ?[A-Z0-9]{4}){2,7}(?: ?[A-Z0-9]{1,3})?\b")
_LONG_HEX = re.compile(r"\b[a-fA-F0-9]{32,}\b")
_DIGIT_RUN = re.compile(r"(?<![\w.])\d(?: ?\d){7,18}(?![\w])")

_RULES: list[tuple[Pattern[str], str]] = [
    (_JWT, "[REDACTED_JWT]"),
    (_BEARER, "Bearer [REDACTED]"),
    (_EMAIL, "[REDACTED_EMAIL]"),
    (_IBAN, "[REDACTED_ACCOUNT]"),
    (_LONG_HEX, "[REDACTED_HEX]"),
    (_DIGIT_RUN, "[REDACTED_NUMBER]"),
]


def redact(text: str) -> str:
    """Remove tokens, secrets, e-mail addresses, IBANs and long digit runs from text."""
    result = _KEY_VALUE.sub(lambda m: f"{m.group(1)}{m.group(2)}[REDACTED]", text)
    for pattern, replacement in _RULES:
        result = pattern.sub(replacement, result)
    return result


class _RequestIdFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = request_id_var.get()
        return True


_installed = False


def setup_logging(level: int = logging.INFO) -> None:
    """Install the redacting record factory and a plain-text root handler (idempotent)."""
    global _installed
    if _installed:
        return
    previous_factory = logging.getLogRecordFactory()

    def factory(*args: object, **kwargs: object) -> logging.LogRecord:
        record = previous_factory(*args, **kwargs)
        try:
            message = record.getMessage()
        except Exception:
            message = str(record.msg)
        record.msg = redact(message)
        record.args = None
        if record.exc_info and record.exc_info[0] is not None and not record.exc_text:
            record.exc_text = redact("".join(traceback.format_exception(*record.exc_info)))
        return record

    logging.setLogRecordFactory(factory)

    root = logging.getLogger()
    root.setLevel(level)
    if not any(getattr(h, "_studyroute", False) for h in root.handlers):
        handler = logging.StreamHandler()
        handler._studyroute = True  # type: ignore[attr-defined]
        handler.addFilter(_RequestIdFilter())
        handler.setFormatter(
            logging.Formatter("%(asctime)s %(levelname)s %(name)s [%(request_id)s] %(message)s")
        )
        root.addHandler(handler)
    _installed = True
