import json
import logging
import os
import sqlite3
from contextlib import contextmanager
from typing import Iterator, List, Optional

from fractal_specifications.contrib.sqlite.specifications import (
    SpecificationNotMappedToSqlite,
    SqliteSpecificationBuilder,
)
from fractal_specifications.generic.operators import EqualsSpecification
from fractal_specifications.generic.specification import Specification

from fractal_repositories.core.repositories import EntityType, Repository
from fractal_repositories.mixins.file_repository_mixin import RootDirMixin
from fractal_repositories.utils.json_encoder import EnhancedEncoder

logger = logging.getLogger(__name__)

_NO_ID_MATCH = object()


class SqliteRepositoryMixin(RootDirMixin, Repository[EntityType]):
    """SQLite-backed repository — a self-contained drop-in for ``FileRepositoryMixin``.

    Stores each entity as a JSON document in a single generic table whose schema
    never changes regardless of the entity's fields::

        CREATE TABLE "<EntityClass>" (id TEXT PRIMARY KEY, data TEXT NOT NULL)

    Because all entity structure lives inside the ``data`` column, there is no
    table schema to manage and nothing to migrate when the entity changes. Old
    rows auto-adapt on read: ``Entity.from_dict`` filters out fields the entity
    no longer has, and rows that can no longer deserialize into the current
    entity (for example after a new *required* field with no default is added)
    are skipped with a warning rather than crashing the read — give new fields a
    default and old rows upgrade transparently on their next write.

    SQLite is the sole source of truth: every read hits the database, nothing is
    cached in memory between calls. Specifications are pushed down into a SQL
    ``WHERE`` clause over the JSON ``data`` column (via
    ``SqliteSpecificationBuilder``), so non-matching rows are filtered in SQLite's
    C layer and never deserialized. The id-keyed paths (``get``/``find_one``/
    ``delete`` by id) use the indexed primary key, and ``count()`` is answered by
    ``SELECT COUNT(*)``.

    Pushdown is applied only when it is *exactly* equivalent to evaluating the
    specification in Python over the stored entities — that is, for JSON-native
    scalar values (``str``/``int``/``float``/``bool``/``None``). Specifications
    whose value is a type that ``asdict`` stores as a string (``Decimal``,
    ``date``, ``datetime``, ``UUID``, ``Enum``) or that use operators SQLite
    cannot faithfully express fall back to Python evaluation, so results are
    always identical to the other repositories — pushdown only ever changes
    performance, never the result. (One deliberate refinement: a range
    comparison against a row whose field is ``null`` excludes that row in SQL,
    where the in-memory path would raise ``TypeError``.) Ordering and pagination
    are applied in Python over the matched rows, because ``Decimal`` (stored as a
    fixed-point string) and other serialized types do not sort naturally in SQL.

    Note that ``count`` reflects stored rows matching the predicate; a row that
    cannot deserialize into the current entity (which ``find`` skips) may still
    be counted until it is rewritten.

    Drop-in with ``FileRepositoryMixin``: same ``root_dir`` constructor, same
    query results. Swapping the base class is the only change an application
    needs.

    Requires no third-party dependencies — ``sqlite3`` ships with Python. SQLite
    provides ACID atomicity, crash-safety, and concurrent-writer locking, so the
    torn-write and corrupt-file handling the file mixin needs does not apply
    here.
    """

    # Deserialization errors that mean "this row is stale relative to the current
    # entity schema" rather than "from_dict has a bug": JSON that is not a
    # mapping or an object missing required fields. Anything else propagates
    # loudly so a genuine bug can't silently hide every row from every read.
    _STALE_ROW_ERRORS = (json.JSONDecodeError, TypeError, ValueError)

    @property
    def _filename(self) -> str:
        return os.path.join(self.root_dir, "db", f"{self.__class__.__name__}.sqlite")

    @property
    def _table(self) -> str:
        # Class names are valid Python identifiers; quoting keeps it a safe SQL
        # identifier regardless.
        return self.__class__.__name__

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        os.makedirs(os.path.dirname(self._filename), exist_ok=True)
        # A fresh connection per operation sidesteps sqlite3's thread-affinity
        # rules; SQLite serializes concurrent access through its own file locks.
        conn = sqlite3.connect(self._filename)
        try:
            conn.execute(
                f'CREATE TABLE IF NOT EXISTS "{self._table}" '
                "(id TEXT PRIMARY KEY, data TEXT NOT NULL)"
            )
            yield conn
            conn.commit()
        finally:
            conn.close()

    def _row_to_entity(self, row_id: str, data: str) -> Optional[EntityType]:
        """Deserialize one row, returning None (with a warning) for stale rows."""
        try:
            return self.entity.from_dict(json.loads(data))
        except self._STALE_ROW_ERRORS as exc:
            logger.warning(
                "Skipping stale row %r in %s: %s",
                row_id,
                self._filename,
                exc,
            )
            return None

    @property
    def _get_entities(self) -> Iterator[EntityType]:
        with self._connect() as conn:
            rows = conn.execute(f'SELECT id, data FROM "{self._table}"').fetchall()
        for row_id, data in rows:
            entity = self._row_to_entity(row_id, data)
            if entity is not None:
                yield entity

    @staticmethod
    def _id_lookup(specification: Optional[Specification]):
        """Return the looked-up id for an ``id``-equality spec, else ``_NO_ID_MATCH``.

        Only a plain ``EqualsSpecification`` on the ``id`` field qualifies for the
        indexed primary-key path. The candidate row is still re-checked with
        ``is_satisfied_by`` so the result matches Python-side filtering exactly
        (the PK is stored as text, so a cross-type query must not falsely match).
        """
        if type(specification) is EqualsSpecification and specification.field == "id":
            return specification.value
        return _NO_ID_MATCH

    def _matching(self, specification: Specification) -> Iterator[EntityType]:
        """Yield entities satisfying the spec, pushing the filter into SQL when possible.

        Falls back to a full scan with Python filtering when the specification
        cannot be translated to SQL, so the result is identical either way.
        """
        try:
            where, params = SqliteSpecificationBuilder.build(specification)
        except SpecificationNotMappedToSqlite:
            for entity in self._get_entities:
                if specification.is_satisfied_by(entity):
                    yield entity
            return
        with self._connect() as conn:
            rows = conn.execute(
                f'SELECT id, data FROM "{self._table}" WHERE {where}', params
            ).fetchall()
        for row_id, data in rows:
            entity = self._row_to_entity(row_id, data)
            if entity is not None:
                yield entity

    def find_one(self, specification: Specification) -> EntityType:
        looked_up = self._id_lookup(specification)
        if looked_up is not _NO_ID_MATCH:
            with self._connect() as conn:
                row = conn.execute(
                    f'SELECT id, data FROM "{self._table}" WHERE id = ?',
                    (str(looked_up),),
                ).fetchone()
            if row is not None:
                entity = self._row_to_entity(row[0], row[1])
                if entity is not None and specification.is_satisfied_by(entity):
                    return entity
            raise self._object_not_found()

        for entity in self._matching(specification):
            return entity
        raise self._object_not_found()

    def find(
        self,
        specification: Optional[Specification] = None,
        *,
        offset: int = 0,
        limit: int = 0,
        order_by: str = "",
    ) -> Iterator[EntityType]:
        if specification:
            entities: List[EntityType] = list(self._matching(specification))
        else:
            entities = list(self._get_entities)

        order_by = order_by or self.order_by
        reverse = order_by.startswith("-")
        if reverse:
            order_by = order_by[1:]
        if order_by:
            entities = sorted(
                entities, key=lambda i: getattr(i, order_by), reverse=reverse
            )

        if limit:
            entities = entities[offset : offset + limit]
        yield from entities

    def count(self, specification: Optional[Specification] = None) -> int:
        try:
            where, params = SqliteSpecificationBuilder.build(specification)
        except SpecificationNotMappedToSqlite:
            return sum(
                1 for e in self._get_entities if specification.is_satisfied_by(e)
            )
        with self._connect() as conn:
            row = conn.execute(
                f'SELECT COUNT(*) FROM "{self._table}" WHERE {where}', params
            ).fetchone()
        return row[0] if row else 0

    def add(self, entity: EntityType) -> EntityType:
        serialized = json.dumps(entity.asdict(), cls=EnhancedEncoder)
        with self._connect() as conn:
            # Last-write-wins on a duplicate id, matching the in-memory mixin's
            # dict-assignment semantics rather than raising on conflict.
            conn.execute(
                f'INSERT OR REPLACE INTO "{self._table}" (id, data) VALUES (?, ?)',
                (str(entity.id), serialized),
            )
        return entity

    def update(self, entity: EntityType, *, upsert=False) -> EntityType:
        if not upsert:
            # Indexed id lookup; raises ObjectNotFoundException if absent.
            self.find_one(Specification.parse(id=entity.id))
        return self.add(entity)

    def remove_one(self, specification: Specification):
        looked_up = self._id_lookup(specification)
        if looked_up is not _NO_ID_MATCH:
            with self._connect() as conn:
                row = conn.execute(
                    f'SELECT id, data FROM "{self._table}" WHERE id = ?',
                    (str(looked_up),),
                ).fetchone()
                entity = self._row_to_entity(row[0], row[1]) if row else None
                if entity is None or not specification.is_satisfied_by(entity):
                    raise self._object_not_found()
                conn.execute(
                    f'DELETE FROM "{self._table}" WHERE id = ?', (str(looked_up),)
                )
            return

        # Mirror the file/in-memory contract: raise if nothing matches, then
        # remove every row that satisfies the specification.
        try:
            where, params = SqliteSpecificationBuilder.build(specification)
        except SpecificationNotMappedToSqlite:
            matching = [
                e for e in self._get_entities if specification.is_satisfied_by(e)
            ]
            if not matching:
                raise self._object_not_found() from None
            with self._connect() as conn:
                conn.executemany(
                    f'DELETE FROM "{self._table}" WHERE id = ?',
                    [(str(e.id),) for e in matching],
                )
            return
        with self._connect() as conn:
            deleted = conn.execute(
                f'DELETE FROM "{self._table}" WHERE {where}', params
            ).rowcount
            if deleted == 0:
                raise self._object_not_found()

    def is_healthy(self) -> bool:
        try:
            with self._connect() as conn:
                conn.execute("SELECT 1").fetchone()
            return True
        except sqlite3.Error:
            return False
