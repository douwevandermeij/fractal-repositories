from typing import Iterator, Optional

from fractal_specifications.generic.operators import NotSpecification
from fractal_specifications.generic.specification import Specification

from fractal_repositories.core.repositories import EntityType, Repository


class CachedRepository(Repository[EntityType]):
    def __init__(
        self, *, main_repository: Repository, cache_repository: Repository, **kwargs
    ):
        super(CachedRepository, self).__init__(**kwargs)
        self.main_repository = main_repository
        self.cache_repository = cache_repository

    def add(self, entity: EntityType) -> EntityType:
        self.main_repository.add(entity)
        self.cache_repository.add(entity)
        return entity

    def update(self, entity: EntityType, *, upsert=False) -> EntityType:
        self.main_repository.update(entity, upsert=upsert)
        self.cache_repository.update(entity, upsert=upsert)
        return entity

    def remove_one(self, specification: Specification):
        self.main_repository.remove_one(specification)
        self.cache_repository.remove_one(specification)

    def find_one(self, specification: Specification) -> EntityType:
        for entity in self.find(specification):
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
        for entity in self.cache_repository.find(
            specification, offset=offset, limit=limit, order_by=order_by
        ):
            yield entity

    def load_cache(self):
        for entity in self.main_repository.find():
            self.cache_repository.add(entity)

    def reload_cache(self):
        added = set([])
        for entity in self.main_repository.find():
            self.cache_repository.update(entity, upsert=True)
            added.add(entity.id)
        for i in list(
            self.cache_repository.find(
                NotSpecification(Specification.parse(id__in=added))
            )
        ):
            self.cache_repository.remove_one(Specification.parse(id=i.id))

    def is_healthy(self) -> bool:
        return self.main_repository.is_healthy() and self.cache_repository.is_healthy()
