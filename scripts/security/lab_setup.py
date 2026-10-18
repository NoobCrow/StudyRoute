"""Attack lab: seed the demo household AND a second, unrelated household in a throwaway database.

    cd backend
    DATA_DIR=/tmp/lab python ../scripts/security/lab_setup.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "backend"))

from app.core.config import get_settings  # noqa: E402
from app.container import build_context  # noqa: E402
from app.domain.auth import create_user, human_actor, find_user_by_email  # noqa: E402
from app.domain.constants import ActorKind  # noqa: E402
from app.domain.recipients import RecipientCreate  # noqa: E402
from app.domain.rules import load_rules  # noqa: E402
from app.scripts.seed import seed_demo  # noqa: E402

settings = get_settings()
ctx = build_context(settings)
seed_demo(ctx, bank_network=True)
password = ctx.settings.demo_password
common = {"passwords": ctx.passwords, "cipher": ctx.cipher, "now": ctx.clock.now()}
with ctx.db.write() as session:
    if find_user_by_email(session, "parent2@lab.studyroute.test") is None:
        parent2 = create_user(
            session, **common, user_id="usr_lab_parent2", email="parent2@lab.studyroute.test",
            display_name="Lab Parent Two", role=ActorKind.PARENT, password=password,
            kyc_status="VERIFIED", address="House 9, Road 1, Chattogram, BD (synthetic)",
        )
        create_user(
            session, **common, user_id="usr_lab_student2", email="student2@lab.studyroute.test",
            display_name="Lab Student Two", role=ActorKind.STUDENT, password=password,
            parent_id=parent2.id, address="Student Halls, Leeds, GB (synthetic)",
        )
        rules = load_rules(session)
        ctx.recipients.create(
            session, human_actor(parent2), rules,
            RecipientCreate(type="UNIVERSITY", display_name="Second Household College (synthetic)",
                            country="GB", bic="WESTGB2L", iban="GB82WEST12345698765432"),
        )
print("lab ready:", settings.database_url)
