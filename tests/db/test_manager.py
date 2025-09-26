from PaperSorter.db import manager


class DummyConnection:
    def __init__(self, *, closed=False, autocommit=True):
        self.closed = int(bool(closed))
        self.autocommit = autocommit
        self.closed_calls = 0

    def close(self):
        self.closed = 1
        self.closed_calls += 1


class FakeThreadedPool:
    initial_connections = []

    def __init__(self, minconn, maxconn, **kwargs):
        self._queue = list(self.initial_connections)
        self.put_calls = []

    def getconn(self):
        if not self._queue:
            raise RuntimeError("No connections left in fake pool")
        return self._queue.pop(0)

    def putconn(self, conn, close=False):
        self.put_calls.append((conn, bool(close)))
        if not close:
            self._queue.append(conn)

    def closeall(self):
        self._queue.clear()


def test_acquire_discards_stale_connections(monkeypatch):
    closed_conn = DummyConnection(closed=True)
    healthy_conn = DummyConnection(autocommit=True)

    FakeThreadedPool.initial_connections = [closed_conn, healthy_conn]
    monkeypatch.setattr(manager, "ThreadedConnectionPool", FakeThreadedPool)

    db_manager = manager.DatabaseManager({}, register_pgvector=False)

    conn = db_manager._acquire()

    assert conn is healthy_conn
    assert healthy_conn.autocommit is False
    assert db_manager._pool.put_calls == [(closed_conn, True)]
