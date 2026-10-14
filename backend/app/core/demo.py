"""Documented SANDBOX demo identities. Synthetic; the .test domain can never receive mail."""

from __future__ import annotations

from app.core.config import Settings

PARENT_EMAIL = "parent@demo.studyroute.test"
STUDENT_EMAIL = "student@demo.studyroute.test"
ADMIN_EMAIL = "admin@demo.studyroute.test"
AI_EMAIL = "ai-agent@demo.studyroute.test"
PARENT_ID = "usr_demo_parent"
STUDENT_ID = "usr_demo_student"
ADMIN_ID = "usr_demo_admin"
AI_ID = "usr_ai_service"


def demo_hints(settings: Settings) -> dict[str, object] | None:
    """What the sign-in page may show. Only in sandbox mode, and only when not switched off."""
    if not (settings.is_sandbox and settings.show_demo_hints):
        return None
    return {
        "accounts": [PARENT_EMAIL, STUDENT_EMAIL, ADMIN_EMAIL],
        "password": settings.demo_password,
        "mfa_code": settings.sandbox_mfa_code,
        "parent_id": PARENT_ID,
    }
