"""Small, reviewed policy catalogue, NOT a bank integration or identity registry.

Source review: 2026-10-17. Scope: MMU self-funded tuition, not International College.
Unknown institutions remain UNVERIFIED and may only use the existing synthetic sandbox.
A declared/name-recognised identity is not verified ownership of a bank account.
"""

from __future__ import annotations

import re
from typing import Any

from sqlalchemy.orm import Session

from app.core import errors
from app.models import Recipient, RecipientInstitution

MMU_ID = "gb-manchester-metropolitan"
SOURCE = "https://www.mmu.ac.uk/student-life/finance/paying-university-fees"
POLICY = {
    "institution_id": MMU_ID,
    "name": "Manchester Metropolitan University",
    "country": "GB",
    "accepted_route": "FLYWIRE",
    "direct_bank_transfer": False,
    "source_url": SOURCE,
    "reviewed_on": "2026-10-17",
    "scope": "Self-funded university tuition; International College is outside this policy.",
    "revision": "2026-10-17.1",
}
MESSAGE = (
    "Manchester Metropolitan University lists Flywire as its official fee payment method "
    "and says direct bank transfers are no longer accepted. StudyRoute has no Flywire "
    "integration. Do not create or submit a direct-bank tuition payment here. "
    "Use the university's official instructions: " + SOURCE
)


def recognized(name: str) -> str | None:
    normal = re.sub(r"[^a-z0-9]+", " ", name.casefold()).strip()
    # Deliberately conservative: ambiguous 'Manchester' or 'MMU' alone is not an identity.
    if "manchester metropolitan university" in normal:
        return MMU_ID
    return None


def validate_declaration(institution_id: str | None, country: str, kind: str) -> None:
    if institution_id is None:
        return
    if institution_id != MMU_ID:
        raise errors.ValidationFailed("Unknown institution policy identifier.")
    if country != "GB" or kind != "UNIVERSITY":
        raise errors.ValidationFailed("This institution policy requires a GB university recipient.")


def binding_id(session: Session, row: Recipient) -> str | None:
    binding = session.get(RecipientInstitution, row.id)
    return binding.institution_id if binding else recognized(row.display_name)


def bind(session: Session, row: Recipient, institution_id: str | None, now: Any) -> None:
    identity = institution_id or recognized(row.display_name)
    if identity and session.get(RecipientInstitution, row.id) is None:
        validate_declaration(identity, row.country, row.type)
        session.add(
            RecipientInstitution(recipient_id=row.id, institution_id=identity, bound_at=now)
        )
        session.flush()


def is_blocked(session: Session, row: Recipient, purpose: str) -> bool:
    return purpose == "TUITION" and binding_id(session, row) == MMU_ID


def status(session: Session, row: Recipient) -> dict[str, Any]:
    known = binding_id(session, row) == MMU_ID
    return {
        "status": "DIRECT_BANK_TUITION_BLOCKED" if known else "UNVERIFIED",
        "policy": POLICY if known else None,
        "identity_verified": False,
        "note": "Declared or conservatively name-recognised identity; never account verification.",
    }
