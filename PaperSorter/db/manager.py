from __future__ import annotations

import threading
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Any, Dict, Iterator, Optional

import psycopg2
import psycopg2.extensions
import psycopg2.extras
from psycopg2 import sql as psycopg2_sql, errors as psycopg2_errors
from psycopg2.pool import ThreadedConnectionPool
from psycopg2.extensions import (
    TRANSACTION_STATUS_ACTIVE,
    TRANSACTION_STATUS_INERROR,
    TRANSACTION_STATUS_INTRANS,
)

try:
    from pgvector.psycopg2 import register_vector
except ImportError:  # pragma: no cover - pgvector should be installed, but keep fallback
    def register_vector(_conn):
        return None

from ..log import log

# Re-export psycopg2 helpers so callers can avoid importing psycopg2 directly
RealDictCursor = psycopg2.extras.RealDictCursor
execute_batch = psycopg2.extras.execute_batch
sql = psycopg2_sql
errors = psycopg2_errors
OperationalError = psycopg2.OperationalError
Connection = psycopg2.extensions.connection
Cursor = psycopg2.extensions.cursor

@dataclass
class PoolConfig:
    minconn: int = 1
    maxconn: int = 10


class DatabaseSession:
    """Context-managed database session that tracks cursors and commits or rolls back."""

    def __init__(self, manager: "DatabaseManager", conn: psycopg2.extensions.connection, autocommit: bool):
        self._manager = manager
        self.connection = conn
        self._autocommit = autocommit
        self._cursors = []
        self._closed = False
        self._original_autocommit = conn.autocommit
        if conn.autocommit != autocommit:
            conn.autocommit = autocommit

    def cursor(self, *, dict_cursor: bool = False) -> psycopg2.extensions.cursor:
        factory = psycopg2.extras.RealDictCursor if dict_cursor else None
        cursor = self.connection.cursor(cursor_factory=factory)
        self._cursors.append(cursor)
        return cursor

    def commit(self) -> None:
        if self._autocommit or self.connection.closed:
            return
        status = self.connection.get_transaction_status()
        if status == TRANSACTION_STATUS_INTRANS:
            self.connection.commit()
        elif status == TRANSACTION_STATUS_ACTIVE:
            # Active queries should be resolved before commit, but commit() will block until ready
            self.connection.commit()

    def rollback(self) -> None:
        if self.connection.closed:
            return
        status = self.connection.get_transaction_status()
        if status in (TRANSACTION_STATUS_ACTIVE, TRANSACTION_STATUS_INTRANS, TRANSACTION_STATUS_INERROR):
            self.connection.rollback()

    def close(self) -> None:
        if self._closed:
            return

        for cursor in self._cursors:
            try:
                cursor.close()
            except Exception:
                continue
        self._cursors.clear()

        try:
            if not self._autocommit and not self.connection.closed:
                status = self.connection.get_transaction_status()
                if status in (TRANSACTION_STATUS_INTRANS, TRANSACTION_STATUS_INERROR):
                    self.connection.rollback()
        except Exception:
            pass

        if not self.connection.closed and self.connection.autocommit != self._original_autocommit:
            self.connection.autocommit = self._original_autocommit

        self._manager._release(self.connection)
        self._closed = True

    def __enter__(self) -> "DatabaseSession":
        return self

    def __exit__(self, exc_type, exc_value, traceback) -> None:
        try:
            if exc_type is None and not self._autocommit and not self.connection.closed:
                try:
                    self.connection.commit()
                except Exception as commit_error:
                    log.error(f"Database commit failed: {commit_error}")
                    raise
            elif exc_type is not None and not self.connection.closed:
                try:
                    self.connection.rollback()
                except Exception:
                    pass
        finally:
            self.close()


class PooledConnection:
    """Legacy-compatible wrapper returning pooled connections with close/commit semantics."""

    def __init__(self, manager: "DatabaseManager", conn: psycopg2.extensions.connection):
        self._manager = manager
        self._conn = conn

    def __getattr__(self, item: str) -> Any:  # Delegate attribute access to the psycopg2 connection
        return getattr(self._conn, item)

    def close(self) -> None:
        if self._conn is None:
            return
        self._manager._release(self._conn)
        self._conn = None

    def __enter__(self) -> "PooledConnection":
        return self

    def __exit__(self, exc_type, exc_value, traceback) -> None:
        try:
            if exc_type is not None and self._conn is not None:
                try:
                    status = self._conn.get_transaction_status()
                    if status in (
                        TRANSACTION_STATUS_ACTIVE,
                        TRANSACTION_STATUS_INTRANS,
                        TRANSACTION_STATUS_INERROR,
                    ):
                        self._conn.rollback()
                except Exception:
                    pass
        finally:
            self.close()


class DatabaseManager:
    """Central access point for PostgreSQL connections with pooling and context helpers."""

    def __init__(
        self,
        connection_settings: Dict[str, Any],
        *,
        pool: Optional[PoolConfig] = None,
        application_name: Optional[str] = None,
        register_pgvector: bool = True,
        default_connect_timeout: int = 10,
    ) -> None:
        settings = dict(connection_settings)

        pool = pool or PoolConfig()
        if pool.maxconn < pool.minconn:
            pool.maxconn = pool.minconn

        if "application_name" not in settings and application_name:
            settings["application_name"] = application_name
        settings.setdefault("connect_timeout", default_connect_timeout)

        self._register_pgvector = register_pgvector
        self._pool = ThreadedConnectionPool(pool.minconn, pool.maxconn, **settings)
        self._lock = threading.Lock()
        self._closed = False

    @classmethod
    def from_config(
        cls,
        db_config: Dict[str, Any],
        *,
        application_name: Optional[str] = None,
        register_pgvector: Optional[bool] = None,
    ) -> "DatabaseManager":
        config = dict(db_config)
        pool_cfg = config.pop("pool", {})
        pool = PoolConfig(
            minconn=int(pool_cfg.get("minconn", pool_cfg.get("min_conn", 1))),
            maxconn=int(pool_cfg.get("maxconn", pool_cfg.get("max_conn", 10))),
        )
        register_flag = register_pgvector if register_pgvector is not None else bool(config.pop("register_pgvector", True))
        default_timeout = int(config.pop("connect_timeout", 10))
        # Remove configuration keys that psycopg2 does not understand
        config.pop("type", None)
        return cls(
            config,
            pool=pool,
            application_name=application_name,
            register_pgvector=register_flag,
            default_connect_timeout=default_timeout,
        )

    def _acquire(self) -> psycopg2.extensions.connection:
        with self._lock:
            if self._closed:
                raise RuntimeError("DatabaseManager pool has been closed")
            conn = self._pool.getconn()
        self._prepare_connection(conn)
        return conn

    def _prepare_connection(self, conn: psycopg2.extensions.connection) -> None:
        if conn.closed:
            return
        if self._register_pgvector:
            try:
                register_vector(conn)
            except Exception as exc:
                log.warning(f"Failed to register pgvector: {exc}")
        if conn.autocommit:
            conn.autocommit = False

    def _release(self, conn: psycopg2.extensions.connection) -> None:
        if conn is None:
            return
        if conn.closed:
            self._pool.putconn(conn, close=True)
            return
        try:
            status = conn.get_transaction_status()
            if status in (
                TRANSACTION_STATUS_ACTIVE,
                TRANSACTION_STATUS_INTRANS,
                TRANSACTION_STATUS_INERROR,
            ):
                conn.rollback()
        except Exception:
            pass
        conn.autocommit = False
        with self._lock:
            if self._closed:
                conn.close()
            else:
                self._pool.putconn(conn)

    def connect(self) -> PooledConnection:
        """Return a pooled connection wrapper for legacy callers."""
        conn = self._acquire()
        return PooledConnection(self, conn)

    @contextmanager
    def session(self, *, autocommit: bool = False) -> Iterator[DatabaseSession]:
        conn = self._acquire()
        session = DatabaseSession(self, conn, autocommit)
        try:
            yield session
            if not autocommit:
                status = session.connection.get_transaction_status()
                if status == TRANSACTION_STATUS_INTRANS:
                    session.commit()
        except Exception:
            try:
                if not autocommit:
                    status = session.connection.get_transaction_status()
                    if status in (
                        TRANSACTION_STATUS_ACTIVE,
                        TRANSACTION_STATUS_INTRANS,
                        TRANSACTION_STATUS_INERROR,
                    ):
                        session.rollback()
            except Exception:
                pass
            raise
        finally:
            session.close()

    @contextmanager
    def cursor(self, *, dict_cursor: bool = False) -> Iterator[psycopg2.extensions.cursor]:
        with self.session() as session:
            cursor = session.cursor(dict_cursor=dict_cursor)
            try:
                yield cursor
                status = session.connection.get_transaction_status()
                if status == TRANSACTION_STATUS_INTRANS:
                    session.commit()
            finally:
                cursor.close()

    def close(self) -> None:
        with self._lock:
            if self._closed:
                return
            self._closed = True
        self._pool.closeall()

    def __del__(self):
        try:
            self.close()
        except Exception:
            pass
