"""Create synthetic demo accounts and recipients. Sandbox only: refuses to run in production.

python -m app.scripts.seed              add the demo data if it is missing
python -m app.scripts.seed --reset      delete the SQLite database first (server must be stopped)
python -m app.scripts.seed --if-empty   used by docker: seed only a brand-new database
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from sqlalchemy.orm import Session

from app.api.context import AppContext
from app.container import build_context
from app.core.config import get_settings
from app.core.demo import (
    ADMIN_EMAIL,
    ADMIN_ID,
    AI_EMAIL,
    AI_ID,
    PARENT_EMAIL,
    PARENT_ID,
    STUDENT_EMAIL,
    STUDENT_ID,
)
from app.domain.auth import create_user, find_user_by_email, human_actor
from app.domain.constants import ActorKind, ActorType
from app.domain.recipients import RecipientCreate
from app.domain.rules import load_rules

UNIVERSITY = RecipientCreate(
    type="UNIVERSITY",
    display_name="University of Example (synthetic)",
    country="GB",
    bic="EXMPGB2L",
    iban="GB08EXMP12345612344821",
)
FAIL_UNIVERSITY = RecipientCreate(
    type="UNIVERSITY",
    display_name="FAIL_TEST University (synthetic)",
    country="GB",
    bic="EXMPGB2L",
    iban="GB13EXMP12345600005555",
)


def seed_demo(ctx: AppContext, *, bank_network: bool = True) -> dict[str, str]:
    """Idempotent: does nothing when the demo parent already exists (apart from adding the
    sandbox bank network to a database that predates it). `bank_network=False` is for tests."""
    now = ctx.clock.now()
    password = ctx.settings.demo_password
    common = {"passwords": ctx.passwords, "cipher": ctx.cipher, "now": now}
    with ctx.db.write() as session:
        if find_user_by_email(session, PARENT_EMAIL) is not None:
            if bank_network:
                _ensure_bank_network(ctx, session)
            return {"parent": PARENT_ID, "student": STUDENT_ID, "admin": ADMIN_ID, "ai": AI_ID}
        parent = create_user(
            session, **common, user_id=PARENT_ID, email=PARENT_EMAIL, display_name="Demo Parent",
            role=ActorKind.PARENT, password=password, kyc_status="NEEDS_DOCUMENTS",
            address="House 12, Road 5, Dhanmondi, Dhaka, BD (synthetic)",
        )  # fmt: skip
        create_user(
            session, **common, user_id=STUDENT_ID, email=STUDENT_EMAIL, display_name="Demo Student",
            role=ActorKind.STUDENT, password=password, parent_id=parent.id,
            address="Student Halls, London, GB (synthetic)",
        )  # fmt: skip
        create_user(
            session, **common, user_id=ADMIN_ID, email=ADMIN_EMAIL, display_name="Demo Reviewer",
            role=ActorKind.ADMIN, password=password,
        )  # fmt: skip
        create_user(
            session, **common, user_id=AI_ID, email=AI_EMAIL, display_name="StudyRoute Assistant",
            role=ActorKind.AI, password=None,
        )  # fmt: skip
        rules = load_rules(session)
        actor = human_actor(parent)
        for recipient in (UNIVERSITY, FAIL_UNIVERSITY):
            ctx.recipients.create(session, actor, rules, recipient)
        if bank_network:
            ctx.bank.ensure_network(session)
        ctx.audit.append(
            session,
            actor_type=ActorType.SYSTEM,
            actor_id="system",
            action="system.seeded",
            detail="Synthetic demo accounts, recipients and sandbox bank accounts created",
        )
    return {"parent": PARENT_ID, "student": STUDENT_ID, "admin": ADMIN_ID, "ai": AI_ID}


def _ensure_bank_network(ctx: AppContext, session: Session) -> int:
    """Add the sandbox banks and bank accounts to a database that predates them. Idempotent."""
    created = ctx.bank.ensure_network(session)
    if created:
        ctx.audit.append(
            session,
            actor_type=ActorType.SYSTEM,
            actor_id="system",
            action="system.bank_network_ready",
            detail=f"{created} synthetic sandbox bank accounts created",
        )
    return created


def ensure_bank_network(ctx: AppContext) -> int:
    with ctx.db.write() as session:
        return _ensure_bank_network(ctx, session)


def _database_is_new(db_file: Path) -> bool:
    return not db_file.exists() or db_file.stat().st_size == 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawTextHelpFormatter
    )
    parser.add_argument("--reset", action="store_true", help="delete the SQLite database first")
    parser.add_argument("--if-empty", action="store_true", help="seed only a brand-new database")
    args = parser.parse_args(argv)

    settings = get_settings()
    if not settings.is_sandbox:
        print("Refusing to seed demo accounts when APP_ENV=production.", file=sys.stderr)
        return 2
    path = Path(settings.database_url.removeprefix("sqlite:///"))
    if args.reset:
        for suffix in ("", "-wal", "-shm"):
            Path(str(path) + suffix).unlink(missing_ok=True)
    elif args.if_empty and not _database_is_new(path):
        ctx = build_context(settings)
        try:
            added = ensure_bank_network(ctx)
        finally:
            ctx.db.dispose()
        note = f" Added {added} sandbox bank accounts." if added else ""
        print(f"Database already has data; skipping seed.{note}")
        return 0
    ctx = build_context(settings)
    try:
        seed_demo(ctx)
    finally:
        ctx.db.dispose()
    print(
        "Demo accounts ready (all synthetic):\n"
        f"  parent   {PARENT_EMAIL}\n  student  {STUDENT_EMAIL}\n  admin    {ADMIN_EMAIL}\n"
        f"  password {settings.demo_password}   MFA code {settings.sandbox_mfa_code}\n"
        "  AI service account has no password: the assistant runs inside the API."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
