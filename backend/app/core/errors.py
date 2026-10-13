"""RFC 7807 problem responses and the error codes from blueprint section 8.6."""

from __future__ import annotations

import logging
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core.logging import request_id_var

logger = logging.getLogger("studyroute.errors")

PROBLEM_CONTENT_TYPE = "application/problem+json"
ERROR_TYPE_BASE = "https://studyroute.example/errors"


class ApiError(Exception):
    """An expected, client-visible error.

    persist=True means the work staged in the current transaction (an audit event, an
    automatic state change) must be committed before the error is returned.
    """

    status: int = 500
    code: str = "INTERNAL"
    title: str = "Internal error"

    def __init__(
        self,
        detail: str | None = None,
        *,
        persist: bool = False,
        extra: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
    ) -> None:
        super().__init__(detail or self.title)
        self.detail = detail or self.title
        self.persist = persist
        self.extra = extra or {}
        self.headers = headers or {}


def _make(status: int, code: str, title: str) -> type[ApiError]:
    return type(
        "".join(part.capitalize() for part in code.split("_")),
        (ApiError,),
        {"status": status, "code": code, "title": title},
    )


BadRequest = _make(400, "BAD_REQUEST", "Bad request")
Unauthenticated = _make(401, "UNAUTHENTICATED", "Authentication required")
Forbidden = _make(403, "FORBIDDEN", "Forbidden")
AiCannotApprove = _make(403, "AI_CANNOT_APPROVE", "The AI cannot approve payments")
MfaRequired = _make(403, "MFA_REQUIRED", "A fresh MFA proof is required")
NotFound = _make(404, "NOT_FOUND", "Not found")
QuoteExpired = _make(409, "QUOTE_EXPIRED", "Quote expired")
InvalidState = _make(409, "INVALID_STATE", "Invalid state for this action")
RequestInProgress = _make(409, "REQUEST_IN_PROGRESS", "Request already in progress")
SummaryMismatch = _make(409, "SUMMARY_MISMATCH", "Approval summary changed")
PayloadTooLarge = _make(413, "PAYLOAD_TOO_LARGE", "Request body too large")
ValidationFailed = _make(422, "VALIDATION_FAILED", "Validation failed")
IdempotencyKeyReused = _make(
    422, "IDEMPOTENCY_KEY_REUSED", "Idempotency-Key reused with a different request"
)
KycNotVerified = _make(422, "KYC_NOT_VERIFIED", "KYC is not verified")
RecipientNotAllowlisted = _make(422, "RECIPIENT_NOT_ALLOWLISTED", "Recipient is not allowlisted")
LimitExceeded = _make(422, "LIMIT_EXCEEDED", "Limit exceeded")
InvalidIban = _make(422, "INVALID_IBAN", "Invalid IBAN")
InvalidBic = _make(422, "INVALID_BIC", "Invalid BIC")
SanctionsHit = _make(422, "SANCTIONS_HIT", "Recipient blocked by sanctions screening")
RateLimited = _make(429, "RATE_LIMITED", "Too many requests")
Internal = _make(500, "INTERNAL", "Internal error")


def problem_body(
    *, status: int, code: str, title: str, detail: str, request_id: str, extra: dict[str, Any]
) -> dict[str, Any]:
    body: dict[str, Any] = {
        "type": f"{ERROR_TYPE_BASE}/{code.lower().replace('_', '-')}",
        "title": title,
        "status": status,
        "code": code,
        "detail": detail,
        "request_id": request_id,
    }
    body.update(extra)
    return body


def problem_response(err: ApiError, request_id: str | None = None) -> JSONResponse:
    body = problem_body(
        status=err.status,
        code=err.code,
        title=err.title,
        detail=err.detail,
        request_id=request_id or request_id_var.get(),
        extra=err.extra,
    )
    return JSONResponse(
        body, status_code=err.status, media_type=PROBLEM_CONTENT_TYPE, headers=err.headers
    )


def _clean_validation_errors(exc: RequestValidationError) -> list[dict[str, Any]]:
    """Report where and why validation failed, never echoing the submitted value."""
    cleaned: list[dict[str, Any]] = []
    for item in exc.errors():
        location = ".".join(str(part) for part in item.get("loc", ()) if part != "body")
        cleaned.append({"field": location or "body", "message": str(item.get("msg", "invalid"))})
    return cleaned


def install_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(ApiError)
    async def _api_error(_: Request, exc: ApiError) -> JSONResponse:
        return problem_response(exc)

    @app.exception_handler(RequestValidationError)
    async def _validation(_: Request, exc: RequestValidationError) -> JSONResponse:
        if any(item.get("type") == "json_invalid" for item in exc.errors()):
            return problem_response(BadRequest("Malformed JSON body."))
        return problem_response(
            ValidationFailed(
                "The request failed validation.", extra={"errors": _clean_validation_errors(exc)}
            )
        )

    @app.exception_handler(StarletteHTTPException)
    async def _http(_: Request, exc: StarletteHTTPException) -> JSONResponse:
        if exc.status_code == 404:
            return problem_response(NotFound("Resource not found."))
        err = BadRequest("Request rejected.")
        err.status = exc.status_code
        err.code = "METHOD_NOT_ALLOWED" if exc.status_code == 405 else err.code
        return problem_response(err)

    @app.exception_handler(Exception)
    async def _unexpected(_: Request, exc: Exception) -> JSONResponse:
        logger.error("unhandled error: %s", type(exc).__name__, exc_info=exc)
        return problem_response(Internal("An unexpected error occurred."))
