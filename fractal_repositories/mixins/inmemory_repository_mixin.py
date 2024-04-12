import uuid
from typing import Dict, Iterator, List, Optional

from fractal_specifications.generic.specification import Specification

from fractal_repositories.core.repositories import (
    EntityType,
    FileRepository,
    Repository,
)


class InMemoryRepositoryMixin(Repository[EntityType]):
    def __init__(self, *args, **kwargs):
        super(InMemoryRepositoryMixin, self).__init__(*args, **kwargs)

        self.entities: Dict[str, EntityType] = {}

    def add(self, entity: EntityType) -> EntityType:
        self.entities[entity.id] = entity
        return entity

    def update(self, entity: EntityType, *, upsert=False) -> EntityType:
        if entity.id in self.entities or upsert:
            return self.add(entity)
        raise self._object_not_found()

    def remove_one(self, specification: Specification):
        if obj := self.find_one(specification):
            if obj.id in self.entities:
                del self.entities[obj.id]

    @property
    def _get_entities(self) -> Iterator[EntityType]:
        for value in self.entities.values():
            yield value

    def find_one(self, specification: Specification) -> EntityType:
        for entity in filter(
            lambda i: specification.is_satisfied_by(i), self._get_entities
        ):
            return entity
        raise self._object_not_found()

    def _filter_entities(
        self, specification: Specification, entities: Iterator[EntityType]
    ) -> List[EntityType]:
        return list(filter(lambda i: specification.is_satisfied_by(i), entities))

    def find(
        self,
        specification: Optional[Specification] = None,
        *,
        offset: int = 0,
        limit: int = 0,
        order_by: str = "",
    ) -> Iterator[EntityType]:
        if specification:
            entities = self._filter_entities(specification, self._get_entities)
        else:
            entities = list(self._get_entities)

        order_by = order_by or self.order_by
        reverse = False
        if order_by.startswith("-"):
            order_by = order_by[1:]
            reverse = True

        if order_by:
            entities = sorted(
                entities, key=lambda i: getattr(i, order_by), reverse=reverse
            )

        if limit:
            entities = list(entities)[offset : offset + limit]
        for entity in entities:
            yield entity

    def is_healthy(self) -> bool:
        return True


class InMemoryFileRepositoryMixin(FileRepository[EntityType]):
    def __init__(self, *args, **kwargs):
        super(InMemoryFileRepositoryMixin, self).__init__(*args, **kwargs)

        self.files: Dict[str, bytes] = {}

    def upload_file(self, data: bytes, content_type: str, reference: str = "") -> str:
        if not reference:
            reference = str(uuid.uuid4())
        self.files[reference] = data
        return reference

    def get_file(self, reference: str) -> bytes:
        return self.files.get(reference, b"")

    def delete_file(self, reference: str) -> bool:
        if reference in self.files:
            del self.files[reference]
            return True
        return False
