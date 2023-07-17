import json
import os
import uuid
from typing import Iterator

from fractal_specifications.generic.operators import NotSpecification
from fractal_specifications.generic.specification import Specification

from fractal_repositories.core.repositories import EntityType, FileRepository
from fractal_repositories.exceptions import ObjectNotFoundException
from fractal_repositories.mixins.inmemory_repository_mixin import (
    InMemoryRepositoryMixin,
)
from fractal_repositories.utils.json_encoder import EnhancedEncoder


class RootDirMixin(object):
    def __init__(self, *, root_dir: str, **kwargs):
        super(RootDirMixin, self).__init__(**kwargs)

        self.root_dir = root_dir


class FileRepositoryMixin(RootDirMixin, InMemoryRepositoryMixin[EntityType]):
    @property
    def _filename(self) -> str:
        return os.path.join(self.root_dir, "db", f"{self.__class__.__name__}.txt")

    @property
    def _get_entities(self) -> Iterator[EntityType]:
        if not os.path.exists(self._filename):
            open(self._filename, "a").close()
        with open(self._filename, "r") as fp:
            for line in fp.readlines():
                yield self.entity.from_dict(json.loads(line))

    def add(self, entity: EntityType) -> EntityType:
        with open(self._filename, "a") as fp:
            fp.write(json.dumps(entity.asdict(), cls=EnhancedEncoder) + "\n")
        return super().add(entity)

    def update(self, entity: EntityType, *, upsert=False) -> EntityType:
        try:
            current = self.find_one(Specification.parse(id=entity.id))
        except ObjectNotFoundException:
            current = None
        if current or upsert:
            if current:
                self.remove_one(Specification.parse(id=current.id))
            return self.add(entity)
        raise self._object_not_found()

    def remove_one(self, specification: Specification):
        super().remove_one(specification)
        entities = list(self.find(NotSpecification(specification)))
        with open(self._filename, "w") as fp:
            fp.writelines(
                [json.dumps(e.asdict(), cls=EnhancedEncoder) + "\n" for e in entities]
            )


class FileFileRepositoryMixin(RootDirMixin, FileRepository):
    def upload_file(self, data: bytes, content_type: str, reference: str = "") -> str:
        if not reference:
            reference = str(uuid.uuid4())
        with open(os.path.join(self.root_dir, "media", reference), "wb") as fp:
            fp.write(data)
        return reference

    def get_file(self, reference: str) -> bytes:
        with open(os.path.join(self.root_dir, "media", reference), "rb") as fp:
            return fp.read()

    def delete_file(self, reference: str) -> bool:
        try:
            os.remove(os.path.join(self.root_dir, "media", reference))
            return True
        except FileNotFoundError:
            return False
