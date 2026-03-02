from fractal_repositories.core.repositories import EntityType, Repository
from fractal_repositories.exceptions import ObjectNotFoundException


class MemoizedRepository(Repository[EntityType]):
    """Wraps any Repository, caching find_one results in-process.

    find_one() results are stored in a per-instance dict keyed by entity.id.
    A secondary _spec_index (spec → entity.id) allows repeated find_one(spec)
    calls to be served from cache without hitting the inner repository.

    Mutations update or evict only the cache entry for the mutated entity;
    unrelated entries remain cached.

    find(), count(), and is_healthy() always delegate directly to the
    inner repository without caching.
    """

    def __init__(self, inner: Repository[EntityType]):
        self.entity = inner.entity
        super().__init__()
        self._inner = inner
        self._cache: dict[str, EntityType] = {}  # entity.id → entity
        self._spec_index: dict = {}  # spec → entity.id

    # --- reads ---

    def find_one(self, specification) -> EntityType:
        entity_id = self._spec_index.get(specification)
        if entity_id is not None:
            if entity_id in self._cache:
                return self._cache[entity_id]
            del self._spec_index[specification]  # stale entry — lazy cleanup
        entity = self._inner.find_one(specification)
        self._cache[entity.id] = entity
        self._spec_index[specification] = entity.id
        return entity

    def find(self, specification=None, *, offset=0, limit=0, order_by=""):
        return self._inner.find(
            specification, offset=offset, limit=limit, order_by=order_by
        )

    def count(self, specification=None):
        return self._inner.count(specification)

    def is_healthy(self):
        return self._inner.is_healthy()

    # --- writes ---

    def add(self, entity: EntityType) -> EntityType:
        return self._inner.add(entity)

    def update(self, entity: EntityType, *, upsert=False) -> EntityType:
        result = self._inner.update(entity, upsert=upsert)
        self._cache[entity.id] = result  # update in place; spec_index stays valid
        return result

    def remove_one(self, specification):
        if specification in self._spec_index:
            entity_id = self._spec_index[specification]
        else:
            try:
                entity_id = self._inner.find_one(specification).id
            except ObjectNotFoundException:
                entity_id = None
        self._inner.remove_one(specification)
        if entity_id is not None:
            self._cache.pop(entity_id, None)
            # Stale _spec_index entries pointing to entity_id are cleaned up lazily.
