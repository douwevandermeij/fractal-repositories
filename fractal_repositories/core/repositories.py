from abc import ABC, abstractmethod
from typing import Generic, Iterator, Optional, Type, TypeVar

from fractal_specifications.generic.specification import Specification

from fractal_repositories.core.entity import Entity
from fractal_repositories.exceptions import ObjectNotFoundException, RepositoryException

EntityType = TypeVar("EntityType", bound=Entity)


class ReadRepository(Generic[EntityType], ABC):
    entity: EntityType
    object_not_found_exception_class: Optional[Type[ObjectNotFoundException]] = None
    order_by: str = ""

    def __init__(self, *args, **kwargs):
        if not hasattr(self, "entity"):
            raise RepositoryException()

    @abstractmethod
    def find_one(self, specification: Specification) -> EntityType:
        raise NotImplementedError

    @abstractmethod
    def find(
        self,
        specification: Optional[Specification] = None,
        *,
        offset: int = 0,
        limit: int = 0,
        order_by: str = "",
    ) -> Iterator[EntityType]:
        raise NotImplementedError

    @abstractmethod
    def is_healthy(self) -> bool:
        raise NotImplementedError

    def _object_not_found(self):
        entity_name = self.entity.__name__ if hasattr(self, "entity") else "Object"
        if self.object_not_found_exception_class:
            return self.object_not_found_exception_class(f"{entity_name} not found!")
        return ObjectNotFoundException(f"{entity_name} not found!")


class WriteRepository(Generic[EntityType], ABC):
    @abstractmethod
    def add(self, entity: EntityType) -> EntityType:
        raise NotImplementedError

    @abstractmethod
    def update(self, entity: EntityType, *, upsert=False) -> EntityType:
        raise NotImplementedError

    @abstractmethod
    def remove_one(self, specification: Specification):
        raise NotImplementedError

    @abstractmethod
    def is_healthy(self) -> bool:
        raise NotImplementedError


class Repository(ReadRepository[EntityType], WriteRepository[EntityType], ABC):
    pass


class FileRepository(Generic[EntityType], ABC):
    @abstractmethod
    def upload_file(self, data: bytes, content_type: str, reference: str = "") -> str:
        raise NotImplementedError

    @abstractmethod
    def get_file(self, reference: str) -> bytes:
        raise NotImplementedError

    @abstractmethod
    def delete_file(self, reference: str) -> bool:
        raise NotImplementedError
