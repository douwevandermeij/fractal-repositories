from typing import Iterator, Optional

import psycopg2
import psycopg2.extras
from fractal_specifications.contrib.postgresql.specifications import (
    PostgresSpecificationBuilder,
)
from fractal_specifications.generic.specification import Specification

from fractal_repositories.core.repositories import (
    EntityType,
    Repository,
)


class PostgresRepositoryMixin(Repository[EntityType]):
    def __init__(
        self,
        postgres_db: str,
        postgres_host: str,
        postgres_password: str,
        postgres_port: str,
        postgres_user: str,
        *args,
        **kwargs,
    ):
        super().__init__(*args, **kwargs)
        self.connection_params = {
            "host": postgres_host,
            "port": postgres_port,
            "database": postgres_db,
            "user": postgres_user,
            "password": postgres_password,
        }
        self.table_name = kwargs.get(
            "table", self.entity.__name__.lower() if self.entity else "entities"  # type: ignore[attr-defined]
        )

    def _get_connection(self):
        return psycopg2.connect(**self.connection_params)

    def add(self, entity: EntityType) -> EntityType:
        with self._get_connection() as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                entity_dict = entity.asdict()
                columns = ", ".join(entity_dict.keys())
                placeholders = ", ".join(["%s"] * len(entity_dict))
                query = (
                    f"INSERT INTO {self.table_name} ({columns}) VALUES ({placeholders})"
                )
                cur.execute(query, list(entity_dict.values()))
                conn.commit()
        return entity

    def update(self, entity: EntityType, *, upsert=False) -> EntityType:
        with self._get_connection() as conn:
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
                    if upsert:
                        return self.add(entity)
                    raise self._object_not_found()

                conn.commit()
        return entity

    def remove_one(self, specification: Specification):
        with self._get_connection() as conn:
            with conn.cursor() as cur:
                where_clause, params = self._build_where_clause(specification)
                query = f"DELETE FROM {self.table_name} WHERE {where_clause}"
                cur.execute(query, params)
                conn.commit()

    def find_one(self, specification: Specification) -> EntityType:
        with self._get_connection() as conn:
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
        with self._get_connection() as conn:
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

                if limit > 0:
                    query += f" LIMIT {limit}"
                    if offset > 0:
                        query += f" OFFSET {offset}"

                cur.execute(query, params)
                for row in cur:
                    if select_clause == "*":
                        yield self._row_to_domain(dict(row))
                    else:
                        yield self._row_to_domain(dict(row))  # type: ignore[misc]

    def count(self, specification: Optional[Specification] = None) -> int:
        with self._get_connection() as conn:
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
            with self._get_connection() as conn:
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
