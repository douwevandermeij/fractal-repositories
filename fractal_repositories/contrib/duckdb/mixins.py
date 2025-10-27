from typing import Iterator, Optional

import duckdb
from fractal_specifications.contrib.duckdb.specifications import (
    DuckDBSpecificationBuilder,
)
from fractal_specifications.generic.specification import Specification

from fractal_repositories.core.repositories import EntityType, Repository


class DuckDBRepositoryMixin(Repository[EntityType]):
    """
    DuckDB Repository Mixin for in-process SQL database operations.

    DuckDB is an in-process analytical database that can run in-memory or persisted to disk.

    Args:
        database: Path to DuckDB database file. Use ":memory:" for in-memory database.
                 If not provided, defaults to in-memory.
        table: Name of the table to use. If not provided, uses entity class name in lowercase.
        read_only: Open database in read-only mode. Defaults to False.
        **kwargs: Additional arguments passed to parent Repository
    """

    def __init__(
        self,
        database: str = ":memory:",
        table: str = "",
        read_only: bool = False,
        *args,
        **kwargs,
    ):
        super().__init__(*args, **kwargs)
        self.database = database
        self.read_only = read_only
        self.connection = duckdb.connect(database, read_only=read_only)

        # Determine table name
        if table:
            self.table_name = table
        elif self.entity:
            self.table_name = self.entity.__name__.lower()  # type: ignore[attr-defined]
        else:
            self.table_name = "entities"

        # Create table if it doesn't exist
        self._ensure_table_exists()

    def _ensure_table_exists(self):
        """Create table schema based on entity if it doesn't exist."""
        if not self.entity or self.read_only:
            return

        # Get entity fields from dataclass
        import dataclasses

        if not dataclasses.is_dataclass(self.entity):
            return

        fields = dataclasses.fields(self.entity)
        columns = []

        for field in fields:
            field_type = field.type
            # Map Python types to DuckDB types
            if field_type is str or field_type == "str":
                sql_type = "VARCHAR"
            elif field_type is int or field_type == "int":
                sql_type = "INTEGER"
            elif field_type is float or field_type == "float":
                sql_type = "DOUBLE"
            elif field_type is bool or field_type == "bool":
                sql_type = "BOOLEAN"
            else:
                # Default to VARCHAR for complex types (will be JSON serialized)
                sql_type = "VARCHAR"

            columns.append(f"{field.name} {sql_type}")

        columns_sql = ", ".join(columns)
        create_table_sql = (
            f"CREATE TABLE IF NOT EXISTS {self.table_name} ({columns_sql})"
        )
        self.connection.execute(create_table_sql)

    def add(self, entity: EntityType) -> EntityType:
        """Add a new entity to the database."""
        entity_dict = entity.asdict()
        columns = ", ".join(entity_dict.keys())
        placeholders = ", ".join(["?" for _ in entity_dict])
        query = f"INSERT INTO {self.table_name} ({columns}) VALUES ({placeholders})"
        self.connection.execute(query, list(entity_dict.values()))
        return entity

    def update(self, entity: EntityType, *, upsert: bool = False) -> EntityType:
        """Update an existing entity or optionally insert if not found."""
        # Check if entity exists first
        exists_query = f"SELECT COUNT(*) FROM {self.table_name} WHERE id = ?"
        exists_result = self.connection.execute(exists_query, [entity.id]).fetchone()

        if not exists_result or exists_result[0] == 0:
            if upsert:
                return self.add(entity)
            raise self._object_not_found()

        # Perform the update
        entity_dict = entity.asdict()
        set_clause = ", ".join([f"{k} = ?" for k in entity_dict.keys() if k != "id"])
        values = [v for k, v in entity_dict.items() if k != "id"]
        values.append(entity.id)

        query = f"UPDATE {self.table_name} SET {set_clause} WHERE id = ?"
        self.connection.execute(query, values)

        return entity

    def remove_one(self, specification: Specification):
        """Remove a single entity matching the specification."""
        where_clause, params = self._build_where_clause(specification)
        query = f"DELETE FROM {self.table_name} WHERE {where_clause}"
        self.connection.execute(query, params)

    def find_one(self, specification: Specification) -> EntityType:
        """Find a single entity matching the specification."""
        where_clause, params = self._build_where_clause(specification)
        query = f"SELECT * FROM {self.table_name} WHERE {where_clause} LIMIT 1"
        result = self.connection.execute(query, params).fetchone()

        if result:
            return self._row_to_domain(result)
        raise self._object_not_found()

    def find(
        self,
        specification: Optional[Specification] = None,
        *,
        offset: int = 0,
        limit: int = 0,
        order_by: str = "",
    ) -> Iterator[EntityType]:
        """Find multiple entities matching the specification."""
        query = f"SELECT * FROM {self.table_name}"
        params: list = []

        if specification:
            where_clause, params = self._build_where_clause(specification)
            query += f" WHERE {where_clause}"

        # Handle ordering
        order_by = order_by or self.order_by
        if order_by:
            direction = "DESC" if order_by.startswith("-") else "ASC"
            column = order_by[1:] if order_by.startswith("-") else order_by
            query += f" ORDER BY {column} {direction}"

        # Handle pagination
        if limit > 0:
            query += f" LIMIT {limit}"
            if offset > 0:
                query += f" OFFSET {offset}"

        result = self.connection.execute(query, params)
        for row in result.fetchall():
            yield self._row_to_domain(row)

    def count(self, specification: Optional[Specification] = None) -> int:
        """Count entities matching the specification."""
        query = f"SELECT COUNT(*) FROM {self.table_name}"
        params: list = []

        if specification:
            where_clause, params = self._build_where_clause(specification)
            query += f" WHERE {where_clause}"

        result = self.connection.execute(query, params).fetchone()
        return result[0] if result else 0

    def is_healthy(self) -> bool:
        """Check if the database connection is healthy."""
        try:
            self.connection.execute("SELECT 1").fetchone()
            return True
        except Exception:
            return False

    def _build_where_clause(self, specification: Specification) -> tuple[str, list]:
        """Build WHERE clause from specification using DuckDBSpecificationBuilder."""
        return DuckDBSpecificationBuilder.build(specification)

    def _row_to_domain(self, row: tuple) -> EntityType:
        """Convert database row tuple to domain entity."""
        # Get column names from the cursor description
        cursor = self.connection.cursor()
        # Execute a dummy query to get column names
        cursor.execute(f"SELECT * FROM {self.table_name} LIMIT 0")
        column_names = [desc[0] for desc in cursor.description]

        # Create dictionary from row tuple and column names
        row_dict = dict(zip(column_names, row, strict=True))
        return self.entity.clean(**row_dict)

    def close(self):
        """Close the database connection."""
        if self.connection:
            self.connection.close()

    def __del__(self):
        """Ensure connection is closed when object is deleted."""
        self.close()
