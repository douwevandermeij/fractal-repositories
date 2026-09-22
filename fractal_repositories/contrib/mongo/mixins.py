from typing import Iterator, Optional, Tuple

from fractal_specifications.contrib.mongo.specifications import (
    MongoSpecificationBuilder,
)
from fractal_specifications.generic.operators import EqualsSpecification
from fractal_specifications.generic.specification import Specification
from pymongo import MongoClient
from pymongo.database import Database
from pymongo.server_api import ServerApi

from fractal_repositories.core.repositories import EntityType, Repository


def setup_mongo_connection(
    host: str = "",
    port: str = "",
    username: str = "",
    password: str = "",
    database: str = "",
    certificate_key_file: str = "",
    uri: str = "",
) -> Tuple[MongoClient, Database]:
    if host == "mongo-mock":
        import mongomock

        client: MongoClient = mongomock.MongoClient()
    elif uri:
        client = MongoClient(uri)
    elif certificate_key_file:
        client = MongoClient(
            f"mongodb+srv://{host}/?authSource=%24external&authMechanism=MONGODB-X509&retryWrites=true&w=majority",
            tls=True,
            tlsCertificateKeyFile=certificate_key_file,
            server_api=ServerApi("1"),
        )
    elif port:
        connection_string = f"mongodb://{username}:{password}@{host}:{port}/?retryWrites=true&w=majority"
        client = MongoClient(connection_string)
    else:
        connection_string = (
            f"mongodb+srv://{username}:{password}@{host}/?retryWrites=true&w=majority"
        )
        client = MongoClient(connection_string)
    db = client[database]
    return client, db


class MongoRepositoryMixin(Repository[EntityType]):
    # A single update_one is atomic at the document level on every deployment,
    # standalone or replica set, so the filter-plus-write below is one step.
    supports_compare_and_swap = True

    def __init__(
        self,
        collection: str = "",
        collection_prefix: str = "",
        *args,
        **kwargs,
    ):
        super().__init__(*args, **kwargs)
        if client := kwargs.get("client"):
            self.client = client
            self.db = client[kwargs.get("database", "")]
        else:
            self.client, self.db = setup_mongo_connection(**kwargs)
        if not collection and self.entity:
            collection = self.entity.__name__  # type: ignore
        if collection_prefix:
            collection = "-".join([collection_prefix, collection])
        self.collection = getattr(self.db, collection.lower().replace(" ", "-"))

    def add(self, entity: EntityType) -> EntityType:
        self.collection.insert_one(entity.asdict())
        return entity

    def update(self, entity: EntityType, *, upsert=False) -> EntityType:
        if obj := self.collection.find_one({"id": entity.id}):
            obj.update(entity.asdict())
            self.collection.update_one(
                {"id": entity.id},
                {"$set": obj},
            )
            return entity
        elif upsert:
            return self.add(entity)
        raise self._object_not_found()

    def compare_and_swap(self, entity: EntityType, *, expected: Specification) -> bool:
        # One update_one: the server matches the document and writes it under
        # the same document-level lock, so nothing can slip between the two.
        # `expected` rides along in the filter, which is what makes the match
        # the comparison.
        result = self.collection.update_one(
            MongoSpecificationBuilder.build(
                EqualsSpecification("id", entity.id) & expected
            ),
            {"$set": entity.asdict()},
        )
        # matched, not modified: a swap that writes back an identical document
        # is still a swap this caller won, and modified_count would report 0.
        return result.matched_count == 1

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
            sort_spec = [(order_by, direction)]
            if order_by != "id":
                # Tiebreaker: without a deterministic secondary key, MongoDB
                # doesn't guarantee stable ordering among documents that tie
                # on order_by, so skip/limit pagination across separate
                # queries can duplicate or drop results between pages.
                sort_spec.append(("id", 1))
            collection = collection.sort(sort_spec)

        if limit:
            collection = collection.skip(offset).limit(limit)

        for obj in collection:
            yield self._obj_to_domain(obj)

    def count(self, specification: Optional[Specification] = None) -> int:
        return self.collection.count_documents(
            MongoSpecificationBuilder.build(specification) or {}
        )

    def is_healthy(self) -> bool:
        return bool(self.client.server_info().get("ok", False))

    def _obj_to_domain(self, obj: dict) -> EntityType:
        return self.entity.clean(**obj)
