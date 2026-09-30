import logging
import threading
import time
from typing import Callable, Dict, Iterator, Optional

from fractal_specifications.generic.specification import Specification

from fractal_repositories.core.repositories import EntityType, Repository
from fractal_repositories.exceptions import ObjectNotFoundException

logger = logging.getLogger(__name__)


def _same(a, b) -> bool:
    return a.asdict() == b.asdict()


class MigratingRepository(Repository[EntityType]):
    """Moves entities from an old store to a new one as they are asked for.

    `primary` is the new store and the one everything is read from and written
    to. `source` is the old store, which is only ever read. An entity asked for
    that `primary` does not have yet is looked up in `source`, written to
    `primary` under the same id, and returned, so a store can be switched
    without migrating it first; `backfill()` copies the rest whenever that
    suits.

    While the old store is still where changes are made, `refresh_after`
    (seconds) keeps the copy current: an entity read from `primary` is read
    from `source` again once that long has passed since its last check in this
    process, and `primary` is updated when it changed. An entity `source` does
    not have is left alone, so everything created in `primary` is already its
    own. Leave `refresh_after` at None to copy each entity once.

    `same(a, b)` decides whether a copy changed (default: equal `asdict()`);
    pass one that ignores bookkeeping fields such as an `updated_on` that is
    set when an entity is built, or every refresh writes.

    `source` failing is logged and never fails a read of something `primary`
    already has.
    """

    def __init__(
        self,
        *,
        primary: Repository[EntityType],
        source: Repository[EntityType],
        refresh_after: Optional[float] = None,
        same: Callable[[EntityType, EntityType], bool] = _same,
        clock: Callable[[], float] = time.monotonic,
        **kwargs,
    ):
        self.entity = primary.entity
        self.object_not_found_exception_class = getattr(
            primary, "object_not_found_exception_class", None
        )
        super().__init__(**kwargs)
        self.primary = primary
        self.source = source
        self.refresh_after = refresh_after
        self.same = same
        self.clock = clock
        self._checked: Dict[object, float] = {}
        self._lock = threading.Lock()

    # --- reads ---

    def find_one(self, specification: Specification) -> EntityType:
        try:
            entity = self.primary.find_one(specification)
        except ObjectNotFoundException:
            migrated = self._migrate_one(specification)
            if migrated is None:
                raise
            return migrated
        return self._refresh(entity)

    def find(
        self,
        specification: Optional[Specification] = None,
        *,
        offset: int = 0,
        limit: int = 0,
        order_by: str = "",
    ) -> Iterator[EntityType]:
        found = list(
            self.primary.find(
                specification, offset=offset, limit=limit, order_by=order_by
            )
        )
        if found:
            for entity in found:
                yield self._refresh(entity)
            return
        # Only a narrowed, first-page query falls back: an unfiltered find would
        # copy the whole store as a side effect of listing it (backfill() is
        # for that), and a later page being empty says nothing about `source`.
        if specification is None or offset:
            return
        try:
            candidates = list(
                self.source.find(specification, limit=limit, order_by=order_by)
            )
        except Exception:
            logger.exception("Could not read %s from the source", self.entity)
            return
        for entity in candidates:
            yield self._store(entity)

    def count(self, specification: Optional[Specification] = None) -> int:
        return self.primary.count(specification)

    def is_healthy(self) -> bool:
        return self.primary.is_healthy()

    # --- writes: the new store only ---

    def add(self, entity: EntityType) -> EntityType:
        return self.primary.add(entity)

    def update(self, entity: EntityType, *, upsert=False) -> EntityType:
        return self.primary.update(entity, upsert=upsert)

    @property
    def supports_compare_and_swap(self) -> bool:  # type: ignore[override]
        return self.primary.supports_compare_and_swap

    def compare_and_swap(self, entity: EntityType, *, expected: Specification) -> bool:
        return self.primary.compare_and_swap(entity, expected=expected)

    def remove_one(self, specification: Specification):
        self.primary.remove_one(specification)

    # --- migration ---

    def backfill(self, specification: Optional[Specification] = None) -> int:
        """Copy what `source` has (all of it, or what matches) into `primary`,
        overwriting what is there; returns how many entities were written."""
        written = 0
        for entity in self.source.find(specification):
            self._store(entity)
            written += 1
        return written

    def _migrate_one(self, specification: Specification) -> Optional[EntityType]:
        try:
            entity = self.source.find_one(specification)
        except ObjectNotFoundException:
            return None
        except Exception:
            logger.exception("Could not read %s from the source", self.entity)
            return None
        return self._store(entity)

    def _store(self, entity: EntityType) -> EntityType:
        self.primary.update(entity, upsert=True)
        self._mark(entity)
        return entity

    def _refresh(self, entity: EntityType) -> EntityType:
        if self.refresh_after is None or not self._due(entity):
            return entity
        try:
            fresh = self.source.find_one(Specification.parse(id=entity.id))
        except ObjectNotFoundException:
            # Not (or no longer) in the old store: the new store owns it.
            self._mark(entity)
            return entity
        except Exception:
            # Try again on the next read rather than wait a full interval.
            logger.exception("Could not refresh %s from the source", self.entity)
            return entity
        self._mark(entity)
        if self.same(entity, fresh):
            return entity
        self.primary.update(fresh, upsert=True)
        return fresh

    def _due(self, entity: EntityType) -> bool:
        checked = self._checked.get(entity.id)
        return checked is None or self.clock() - checked >= self.refresh_after

    def _mark(self, entity: EntityType) -> None:
        with self._lock:
            self._checked[entity.id] = self.clock()
