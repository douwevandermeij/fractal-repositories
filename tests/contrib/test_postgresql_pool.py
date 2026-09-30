"""Connections come from a bounded pool and always go back to it.

Before, every call opened a new connection with psycopg2.connect and relied on
garbage collection to close it (`with conn:` only ends the transaction), and
`find` held its connection until the caller had read every row. Under load that
exhausted the server's max_connections ("too many clients already").
"""

import threading
import time
from abc import ABC
from dataclasses import dataclass
from unittest.mock import MagicMock, patch

import psycopg2
import pytest
from fractal_specifications.generic.specification import Specification

from fractal_repositories.contrib.postgresql.mixins import (
    PostgresPoolExhausted,
    PostgresRepositoryMixin,
)
from fractal_repositories.core.entity import Entity
from fractal_repositories.core.repositories import Repository


@dataclass
class Thing(Entity):
    id: str
    name: str = "thing"


class ThingRepository(Repository[Thing], ABC):
    entity = Thing


class PostgresThingRepository(ThingRepository, PostgresRepositoryMixin[Thing]): ...


class FakeServer:
    """Stands in for psycopg2.connect: hands out connections, counts how many
    exist and how many are checked out at once."""

    def __init__(self, rows=None, rowcount=1):
        self.rows = rows or []
        self.rowcount = rowcount
        self.connections = []
        self.lock = threading.Lock()
        self.in_use = 0
        self.max_in_use = 0

    def connect(self, **params):
        conn = MagicMock(name=f"conn{len(self.connections)}")
        conn.closed = 0
        conn.params = params
        conn.__enter__ = MagicMock(side_effect=lambda: self._checkout(conn))
        conn.__exit__ = MagicMock(side_effect=lambda *a: self._checkin())
        # A dict cursor for rows (cursor_factory=RealDictCursor), a plain one
        # for count(), which reads fetchone()[0].
        cursor = MagicMock()
        cursor.fetchall.return_value = [dict(r) for r in self.rows]
        cursor.fetchone.return_value = dict(self.rows[0]) if self.rows else None
        cursor.rowcount = self.rowcount
        plain = MagicMock()
        plain.fetchone.return_value = (len(self.rows),)

        def open_cursor(*args, **kwargs):
            chosen = cursor if kwargs.get("cursor_factory") else plain
            context = MagicMock()
            context.__enter__ = MagicMock(return_value=chosen)
            context.__exit__ = MagicMock(return_value=False)
            return context

        conn.cursor.side_effect = open_cursor
        conn.the_cursor = cursor
        self.connections.append(conn)
        return conn

    def _checkout(self, conn):
        with self.lock:
            self.in_use += 1
            self.max_in_use = max(self.max_in_use, self.in_use)
        return conn

    def _checkin(self):
        with self.lock:
            self.in_use -= 1
        return False


@pytest.fixture(autouse=True)
def fresh_pools():
    PostgresRepositoryMixin.close_all_pools()
    yield
    PostgresRepositoryMixin.close_all_pools()


def _repo(**settings):
    return PostgresThingRepository(
        postgres_host="db",
        postgres_port="5432",
        postgres_db="app",
        postgres_user="app",
        postgres_password="secret",
        table="things",
        **settings,
    )


def _server(**kwargs):
    server = FakeServer(**kwargs)
    return server, patch("psycopg2.connect", side_effect=server.connect)


def test_calls_reuse_one_connection():
    server, connect = _server(rows=[{"id": "1", "name": "a"}])
    with connect:
        repo = _repo()
        repo.add(Thing(id="1"))
        repo.find_one(Specification.parse(id="1"))
        list(repo.find())
        repo.count()

    assert len(server.connections) == 1


def test_repositories_with_the_same_settings_share_a_pool():
    server, connect = _server()
    with connect:
        _repo().count()
        _repo().count()

    assert len(server.connections) == 1


def test_concurrent_calls_never_exceed_the_maximum():
    server, connect = _server(rows=[{"id": "1", "name": "a"}])

    def slow_fetchall(*args):
        time.sleep(0.02)
        return [{"id": "1", "name": "a"}]

    with connect:
        repo = _repo(postgres_max_connections=3)
        original = server.connect

        def connect_slow(**params):
            conn = original(**params)
            conn.the_cursor.fetchall.side_effect = slow_fetchall
            return conn

        with patch("psycopg2.connect", side_effect=connect_slow):
            threads = [
                threading.Thread(target=lambda: list(repo.find())) for _ in range(12)
            ]
            for t in threads:
                t.start()
            for t in threads:
                t.join()

    assert server.max_in_use <= 3
    assert len(server.connections) <= 3


def test_a_connection_goes_back_after_an_exception():
    server, connect = _server()
    with connect:
        repo = _repo(postgres_max_connections=1, postgres_acquire_timeout=0.2)
        with pytest.raises(repo._object_not_found().__class__):
            repo.find_one(Specification.parse(id="missing"))

        repo.count()  # would time out if the failed call had kept it

    assert len(server.connections) == 1
    assert server.in_use == 0


def test_an_abandoned_find_holds_no_connection():
    server, connect = _server(rows=[{"id": "1", "name": "a"}, {"id": "2", "name": "b"}])
    with connect:
        repo = _repo(postgres_max_connections=1, postgres_acquire_timeout=0.2)
        results = repo.find()
        first = next(results)  # stop after one result, keep the iterator

        repo.count()  # the only connection must be free again

    assert first.id == "1"
    assert server.in_use == 0


def test_upsert_needs_only_one_connection():
    server, connect = _server(rowcount=0)
    with connect:
        repo = _repo(postgres_max_connections=1, postgres_acquire_timeout=0.2)
        repo.update(Thing(id="new"), upsert=True)

    cursor = server.connections[0].the_cursor
    statements = [call.args[0] for call in cursor.execute.call_args_list]
    assert statements[0].startswith("UPDATE things")
    assert statements[1].startswith("INSERT INTO things")


def test_a_call_waits_and_then_gives_up_when_every_connection_is_busy():
    server, connect = _server()
    with connect:
        repo = _repo(postgres_max_connections=1, postgres_acquire_timeout=0.1)
        pool = repo._pool()
        held = pool.getconn()
        try:
            with pytest.raises(PostgresPoolExhausted):
                repo.count()
        finally:
            pool.putconn(held)
        repo.count()


def test_a_broken_connection_is_closed_not_reused():
    server, connect = _server()
    with connect:
        repo = _repo()
        with patch.object(
            PostgresThingRepository,
            "_build_where_clause",
            side_effect=psycopg2.OperationalError("server closed the connection"),
        ):
            with pytest.raises(psycopg2.OperationalError):
                repo.count(Specification.parse(id="1"))
        repo.count()

    assert len(server.connections) == 2


def test_connections_carry_an_application_name():
    server, connect = _server()
    with connect:
        _repo(postgres_application_name="pulse-dagster-meta").count()

    assert server.connections[0].params["application_name"] == "pulse-dagster-meta"
