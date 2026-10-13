"""Shared fixtures."""

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path

import pytest

from app.core.clock import FakeClock
from app.core.db import Database

START = datetime(2026, 10, 14, 5, 0, tzinfo=UTC)  # a Wednesday, 11:00 in Dhaka


@pytest.fixture
def clock() -> FakeClock:
    return FakeClock(START)


@pytest.fixture
def db_path(tmp_path: Path) -> Path:
    return tmp_path / "test.db"


@pytest.fixture
def db(db_path: Path) -> Iterator[Database]:
    database = Database(f"sqlite:///{db_path.as_posix()}")
    database.create_schema()
    yield database
    database.dispose()
