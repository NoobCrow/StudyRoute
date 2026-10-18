"""The pre-submission scanner catches planted secrets and accepts synthetic data."""

from __future__ import annotations

import importlib.util
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "scan_repo.py"
spec = importlib.util.spec_from_file_location("scan_repo", SCRIPT)
assert spec and spec.loader
scan_repo = importlib.util.module_from_spec(spec)
spec.loader.exec_module(scan_repo)

FAKE_PEM = "-----BEGIN " + "PRIVATE KEY-----"
FAKE_KEY = "sk-" + "ant-" + "a" * 30


def test_planted_secrets_are_flagged() -> None:
    text = f'pem = """{FAKE_PEM}"""\nkey = "{FAKE_KEY}"\nmail alice@bank.com\n# TO' + "DO later\n"
    found = "\n".join(scan_repo.scan_text("app/x.py", text))
    for label in ("private key block", "API key", "real domain", "TODO marker"):
        assert label in found


def test_synthetic_data_is_accepted() -> None:
    text = "parent@demo.studyroute.test and a@b.test, IBAN GB08EXMP12345612344821, rate 1.58"
    assert scan_repo.scan_text("app/x.py", text) == []


def test_the_current_repository_is_clean() -> None:
    hits = [h for path in scan_repo.tracked_files() for h in scan_repo.scan_file(path)]
    assert hits == []
