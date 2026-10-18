"""Traceability: every blueprint test ID (T01..T24, section 16) must have at least one test."""

from __future__ import annotations

import re
from pathlib import Path

TESTS = Path(__file__).parent
EXPECTED = {f"T{n:02d}" for n in range(1, 25)}


def covered_ids() -> set[str]:
    found: set[str] = set()
    for path in TESTS.glob("test_*.py"):
        found.update(re.findall(r"def test_(T\d\d)_", path.read_text(encoding="utf-8")))
    return found


def test_every_blueprint_test_id_has_a_test() -> None:
    missing = sorted(EXPECTED - covered_ids())
    assert not missing, f"No test named test_<ID>_... for: {missing}"


def test_no_unknown_test_ids() -> None:
    assert covered_ids() <= EXPECTED
