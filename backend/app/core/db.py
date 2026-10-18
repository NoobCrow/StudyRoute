"""Database engines and sessions.

SQLite is the tested path. Writers use BEGIN IMMEDIATE so two writers never interleave
(this is what keeps the audit hash chain linear). Readers use a separate query-only engine.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from sqlalchemy import String, create_engine, event, text
from sqlalchemy.engine import Engine
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker
from sqlalchemy.types import TypeDecorator

from app.core.errors import ApiError, RequestInProgress

_DT_FORMAT = "%Y-%m-%dT%H:%M:%S.%fZ"


class UTCDateTime(TypeDecorator[datetime]):
    """Stores aware datetimes as fixed-width ISO 8601 UTC text. Sorts correctly as text."""

    impl = String(27)
    cache_ok = True

    def process_bind_param(self, value: datetime | None, dialect: Any) -> str | None:
        if value is None:
            return None
        if value.tzinfo is None:
            raise ValueError("naive datetime refused: use timezone-aware UTC")
        return value.astimezone(UTC).strftime(_DT_FORMAT)

    def process_result_value(self, value: str | None, dialect: Any) -> datetime | None:
        if value is None:
            return None
        return datetime.strptime(value, _DT_FORMAT).replace(tzinfo=UTC)


class Base(DeclarativeBase):
    pass


AUDIT_TRIGGERS = (
    """CREATE TRIGGER IF NOT EXISTS audit_events_no_update BEFORE UPDATE ON audit_events
       BEGIN SELECT RAISE(ABORT, 'audit_events is append-only: UPDATE blocked'); END""",
    """CREATE TRIGGER IF NOT EXISTS audit_events_no_delete BEFORE DELETE ON audit_events
       BEGIN SELECT RAISE(ABORT, 'audit_events is append-only: DELETE blocked'); END""",
    """CREATE TRIGGER IF NOT EXISTS ledger_entries_no_update BEFORE UPDATE ON ledger_entries
       BEGIN SELECT RAISE(ABORT, 'ledger_entries is append-only: UPDATE blocked'); END""",
    """CREATE TRIGGER IF NOT EXISTS ledger_entries_no_delete BEFORE DELETE ON ledger_entries
       BEGIN SELECT RAISE(ABORT, 'ledger_entries is append-only: DELETE blocked'); END""",
    """CREATE TRIGGER IF NOT EXISTS ledger_journals_no_update BEFORE UPDATE ON ledger_journals
       BEGIN SELECT RAISE(ABORT, 'ledger_journals is append-only: UPDATE blocked'); END""",
    """CREATE TRIGGER IF NOT EXISTS ledger_journals_no_delete BEFORE DELETE ON ledger_journals
       BEGIN SELECT RAISE(ABORT, 'ledger_journals is append-only: DELETE blocked'); END""",
    """CREATE TRIGGER IF NOT EXISTS chain_log_no_update BEFORE UPDATE ON chain_log
       BEGIN SELECT RAISE(ABORT, 'chain_log is append-only: UPDATE blocked'); END""",
    """CREATE TRIGGER IF NOT EXISTS chain_log_no_delete BEFORE DELETE ON chain_log
       BEGIN SELECT RAISE(ABORT, 'chain_log is append-only: DELETE blocked'); END""",
)


def _build_sqlite_engine(url: str, *, writer: bool) -> Engine:
    engine = create_engine(url, connect_args={"check_same_thread": False, "timeout": 30})

    @event.listens_for(engine, "connect")
    def _on_connect(dbapi_connection: sqlite3.Connection, _record: Any) -> None:
        dbapi_connection.isolation_level = None  # we emit BEGIN ourselves
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.execute("PRAGMA busy_timeout=30000")
        if writer:
            cursor.execute("PRAGMA journal_mode=WAL")
            cursor.execute("PRAGMA synchronous=NORMAL")
        else:
            cursor.execute("PRAGMA query_only=ON")
        cursor.close()

    @event.listens_for(engine, "begin")
    def _on_begin(conn: Any) -> None:
        conn.exec_driver_sql("BEGIN IMMEDIATE" if writer else "BEGIN")

    return engine


class Database:
    def __init__(self, url: str) -> None:
        self.url = url
        self.is_sqlite = url.startswith("sqlite")
        if self.is_sqlite:
            Path(self.sqlite_path()).parent.mkdir(parents=True, exist_ok=True)
            self.write_engine = _build_sqlite_engine(url, writer=True)
            self.read_engine = _build_sqlite_engine(url, writer=False)
        else:
            self.write_engine = create_engine(url, pool_pre_ping=True)
            self.read_engine = self.write_engine
        self._write_factory = sessionmaker(self.write_engine, expire_on_commit=False)
        self._read_factory = sessionmaker(self.read_engine, expire_on_commit=False)

    def sqlite_path(self) -> str:
        prefix = "sqlite:///"
        return self.url[len(prefix) :] if self.url.startswith(prefix) else ""

    def create_schema(self) -> None:
        import app.models  # noqa: F401  (register tables)

        Base.metadata.create_all(self.write_engine)
        if self.is_sqlite:
            with self.write_engine.begin() as conn:
                for statement in AUDIT_TRIGGERS:
                    conn.execute(text(statement))

    @contextmanager
    def write(self) -> Iterator[Session]:
        """One write transaction. Commits on success; ApiError(persist=True) also commits."""
        session = self._write_factory()
        try:
            yield session
            session.commit()
        except ApiError as err:
            if err.persist:
                session.commit()
            else:
                session.rollback()
            raise
        except OperationalError as exc:
            session.rollback()
            if "locked" in str(exc).lower():
                raise RequestInProgress("The database is busy. Retry with the same key.") from exc
            raise
        except BaseException:
            session.rollback()
            raise
        finally:
            session.close()

    @contextmanager
    def read(self) -> Iterator[Session]:
        session = self._read_factory()
        try:
            yield session
        finally:
            session.rollback()
            session.close()

    def dispose(self) -> None:
        self.write_engine.dispose()
        if self.read_engine is not self.write_engine:
            self.read_engine.dispose()
