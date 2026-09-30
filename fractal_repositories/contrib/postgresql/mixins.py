import threading
from contextlib import contextmanager
from typing import Iterator, Optional

import psycopg2
import psycopg2.extras
import psycopg2.pool
from fractal_specifications.contrib.postgresql.specifications import (
    PostgresSpecificationBuilder,
)
from fractal_specifications.generic.specification import Specification

from fractal_repositories.core.repositories import (
    EntityType,
    Repository,
)

DEFAULT_MIN_CONNECTIONS = 0
DEFAULT_MAX_CONNECTIONS = 5
DEFAULT_ACQUIRE_TIMEOUT = 30.0
DEFAULT_APPLICATION_NAME = "fractal-repositories"


class PostgresPoolExhausted(Exception):
    """Every pooled connection stayed in use for the whole acquire timeout."""


class _Pool:
    """A thread-safe connection pool that waits for a free connection.

    psycopg2's ThreadedConnectionPool raises the moment `maxconn` connections
    are out; a web app serving requests from a threadpool wants the request to
    wait its turn instead. The semaphore does the waiting, the pool the reuse.
    """

    def __init__(self, minconn: int, maxconn: int, timeout: float, **params):
        self.timeout = timeout
        self._slots = threading.BoundedSemaphore(maxconn)
        self._pool = psycopg2.pool.ThreadedConnectionPool(minconn, maxconn, **params)
        # psycopg2 opens `minconn` connections up front and closes every
        # connection handed back beyond `minconn`, so a pool created with the
        # minimum it should open would reuse none of the rest. Open lazily, but
        # keep every connection once opened (up to `maxconn`).
        self._pool.minconn = maxconn

    def getconn(self):
        if not self._slots.acquire(timeout=self.timeout):
            raise PostgresPoolExhausted(
                f"No Postgres connection became free within {self.timeout}s"
            )
        try:
            return self._pool.getconn()
        except Exception:
            self._slots.release()
            raise

    def putconn(self, conn, *, close: bool = False):
        try:
            self._pool.putconn(conn, close=close or bool(getattr(conn, "closed", 0)))
        finally:
            self._slots.release()

    def closeall(self):
        self._pool.closeall()


class PostgresRepositoryMixin(Repository[EntityType]):
    """A repository on a Postgres table.

    Connections come from a pool shared by every repository with the same
    connection settings in this process, so a request costs no new connection
    and the number of connections to the server stays bounded by
    `postgres_max_connections` (default 5) per process and setting. They are
    opened on demand (`postgres_min_connections` up front, default 0) and kept
    open for reuse. A call that
    finds every connection in use waits up to `postgres_acquire_timeout`
    seconds for one. `postgres_application_name` names the connections in
    `pg_stat_activity`.
    """

    _pools: dict = {}
    _pools_lock = threading.Lock()

    def __init__(
        self,
        postgres_db: str,
        postgres_host: str,
        postgres_password: str,
        postgres_port: str,
        postgres_user: str,
        *args,
        postgres_min_connections: int = DEFAULT_MIN_CONNECTIONS,
        postgres_max_connections: int = DEFAULT_MAX_CONNECTIONS,
        postgres_acquire_timeout: float = DEFAULT_ACQUIRE_TIMEOUT,
        postgres_application_name: str = DEFAULT_APPLICATION_NAME,
        **kwargs,
    ):
        super().__init__(*args, **kwargs)
        self.connection_params = {
            "host": postgres_host,
            "port": postgres_port,
            "database": postgres_db,
            "user": postgres_user,
            "password": postgres_password,
            "application_name": postgres_application_name,
        }
        self.pool_settings = (
            int(postgres_min_connections),
            max(1, int(postgres_max_connections)),
            float(postgres_acquire_timeout),
        )
        self.table_name = kwargs.get(
            "table", self.entity.__name__.lower() if self.entity else "entities"  # type: ignore[attr-defined]
        )

    def _pool(self) -> _Pool:
        key = (tuple(sorted(self.connection_params.items())), self.pool_settings)
        pool = self._pools.get(key)
        if pool is None:
            with self._pools_lock:
                pool = self._pools.get(key)
                if pool is None:
                    minconn, maxconn, timeout = self.pool_settings
                    pool = _Pool(minconn, maxconn, timeout, **self.connection_params)
                    PostgresRepositoryMixin._pools[key] = pool
        return pool

    @classmethod
    def close_all_pools(cls):
        """Close every pooled connection in this process (a shutdown hook)."""
        with PostgresRepositoryMixin._pools_lock:
            pools = list(PostgresRepositoryMixin._pools.values())
            PostgresRepositoryMixin._pools = {}
        for pool in pools:
            pool.closeall()

    @contextmanager
    def _connection(self):
        """A pooled connection for one unit of work.

        The transaction is committed when the block succeeds and rolled back
        when it raises (psycopg2's `with conn:`); either way the connection goes
        back to the pool, closed if it broke. `with psycopg2.connect()` alone,
        as before, ended the transaction but left the connection open until the
        object was garbage collected.
        """
        pool = self._pool()
        conn = pool.getconn()
        broken = False
        try:
            with conn as transaction:
                yield transaction
        except (psycopg2.OperationalError, psycopg2.InterfaceError):
            broken = True
            raise
        finally:
            pool.putconn(conn, close=broken)

    def _get_connection(self):
        """Deprecated: an unpooled connection the caller must close itself."""
        return psycopg2.connect(**self.connection_params)

    def add(self, entity: EntityType) -> EntityType:
        with self._connection() as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                self._insert(cur, entity)
                conn.commit()
        return entity

    def _insert(self, cur, entity: EntityType) -> None:
        entity_dict = entity.asdict()
        columns = ", ".join(entity_dict.keys())
        placeholders = ", ".join(["%s"] * len(entity_dict))
        query = f"INSERT INTO {self.table_name} ({columns}) VALUES ({placeholders})"
        cur.execute(query, list(entity_dict.values()))

    def update(self, entity: EntityType, *, upsert=False) -> EntityType:
        with self._connection() as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                entity_dict = entity.asdict()
                set_clause = ", ".join(
                    [f"{k} = %s" for k in entity_dict.keys() if k != "id"]
                )
                values = [v for k, v in entity_dict.items() if k != "id"]
                values.append(entity.id)

                query = f"UPDATE {self.table_name} SET {set_clause} WHERE id = %s"
                cur.execute(query, values)

                if cur.rowcount == 0:
                    if not upsert:
                        raise self._object_not_found()
                    # On the same connection: asking the pool for a second one
                    # while holding this one can wait on itself.
                    self._insert(cur, entity)

                conn.commit()
        return entity

    def remove_one(self, specification: Specification):
        with self._connection() as conn:
            with conn.cursor() as cur:
                where_clause, params = self._build_where_clause(specification)
                query = f"DELETE FROM {self.table_name} WHERE {where_clause}"
                cur.execute(query, params)
                conn.commit()

    def find_one(self, specification: Specification) -> EntityType:
        with self._connection() as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                where_clause, params = self._build_where_clause(specification)
                query = f"SELECT * FROM {self.table_name} WHERE {where_clause} LIMIT 1"
                cur.execute(query, params)
                row = cur.fetchone()
                if row:
                    return self._row_to_domain(dict(row))
                raise self._object_not_found()

    def find(
        self,
        specification: Optional[Specification] = None,
        *,
        offset: int = 0,
        limit: int = 0,
        order_by: str = "",
        select: Optional[list[str]] = None,
    ) -> Iterator[EntityType]:
        select_clause: str
        if select:
            select_clause = ", ".join(select)
        else:
            select_clause = "*"
        with self._connection() as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                query = f"SELECT {select_clause} FROM {self.table_name}"
                params: list = []

                if specification:
                    where_clause, params = self._build_where_clause(specification)
                    query += f" WHERE {where_clause}"

                order_by = order_by or self.order_by
                if order_by:
                    direction = "DESC" if order_by.startswith("-") else "ASC"
                    column = order_by[1:] if order_by.startswith("-") else order_by
                    query += f" ORDER BY {column} {direction}"
                    if column != "id":
                        # Tiebreaker: without a deterministic secondary key,
                        # ties on the sort column have no guaranteed order
                        # across separate LIMIT/OFFSET queries, so pagination
                        # can duplicate or drop rows between pages.
                        query += ", id ASC"

                if limit > 0:
                    query += f" LIMIT {limit}"
                    if offset > 0:
                        query += f" OFFSET {offset}"

                cur.execute(query, params)
                rows = cur.fetchall()
        # Yielded after the connection is back in the pool: a caller that stops
        # after the first result (or never finishes) no longer holds a
        # connection, and an open transaction, until the generator is collected.
        for row in rows:
            yield self._row_to_domain(dict(row))

    def count(self, specification: Optional[Specification] = None) -> int:
        with self._connection() as conn:
            with conn.cursor() as cur:
                query = f"SELECT COUNT(*) FROM {self.table_name}"
                params: list = []

                if specification:
                    where_clause, params = self._build_where_clause(specification)
                    query += f" WHERE {where_clause}"

                cur.execute(query, params)
                return cur.fetchone()[0]

    def is_healthy(self) -> bool:
        try:
            with self._connection() as conn:
                with conn.cursor() as cur:
                    cur.execute("SELECT 1")
                    return True
        except Exception:
            return False

    def _build_where_clause(self, specification: Specification) -> tuple[str, list]:
        """Build WHERE clause using PostgresSpecificationBuilder."""
        return PostgresSpecificationBuilder.build(specification)

    def _row_to_domain(self, row: dict) -> EntityType:
        return self.entity.clean(**row)
