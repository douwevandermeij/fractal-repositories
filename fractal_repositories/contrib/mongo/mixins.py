from typing import Iterator, Optional, Tuple

from fractal_specifications.contrib.mongo.specifications import (
    MongoSpecificationBuilder,
)
from fractal_specifications.generic.specification import Specification
from pymongo import MongoClient
from pymongo.database import Database

from fractal_repositories.core.repositories import EntityType, Repository


def setup_mongo_connection(
    host: str, port: str, username: str, password: str, database: str
) -> Tuple[MongoClient, Database]:
    if host == "mongo-mock":
        import mongomock

        client: MongoClient = mongomock.MongoClient()
    elif port:
        connection_string = f"mongodb://{username}:{password}@{host}:{port}/?retryWrites=true&w=majority"
        client = MongoClient(connection_string)
    else:
        connection_string = (
            f"mongodb+srv://{username}:{password}@p{host}/?retryWrites=true&w=majority"
        )
        client = MongoClient(connection_string)
    db = client[database]
    return client, db


class MongoRepositoryMixin(Repository[EntityType]):
    def __init__(
        self,
        host: str,
        port: str,
        username: str,
        password: str,
        database: str,
        collection: str = "",
        *args,
        **kwargs,
    ):
        super().__init__(*args, **kwargs)
        self.client, self.db = setup_mongo_connection(
            host, port, username, password, database
        )
        if not collection and self.entity:
            collection = self.entity.__name__  # type: ignore
        self.collection = getattr(self.db, collection.lower().replace(" ", "-"))

    def add(self, entity: EntityType) -> EntityType:
        self.collection.insert_one(entity.asdict())
        return entity

    def update(self, entity: EntityType, upsert=False) -> EntityType:
        if obj := self.collection.find_one(
            dict(
                id=entity.id,
            )
        ):
            obj.update(entity.asdict())
            self.collection.update_one(
                dict(
                    id=entity.id,
                ),
                {"$set": obj},
            )
            return entity
        elif upsert:
            return self.add(entity)
        raise self._object_not_found()

    def remove_one(self, specification: Specification):
        self.collection.delete_one(MongoSpecificationBuilder.build(specification))

    def find_one(self, specification: Specification) -> EntityType:
        for obj in self.collection.find(MongoSpecificationBuilder.build(specification)):
            return self._obj_to_domain(obj)
        raise self._object_not_found()

    def find(
        self,
        specification: Optional[Specification] = None,
        *,
        offset: int = 0,
        limit: int = 0,
        order_by: str = "",
    ) -> Iterator[EntityType]:
        order_by = order_by or self.order_by
        direction = 1
        if order_by.startswith("-"):
            order_by = order_by[1:]
            direction = -1

        collection = self.collection.find(
            MongoSpecificationBuilder.build(specification)
        )

        if order_by:
            collection = collection.sort({order_by: direction})

        if limit:
            collection = collection.skip(offset).limit(limit)

        for obj in collection.sort(order_by, direction):
            yield self._obj_to_domain(obj)

    def is_healthy(self) -> bool:
        return bool(self.client.server_info().get("ok", False))

    def _obj_to_domain(self, obj: dict) -> EntityType:
        return self.entity.clean(**obj)
