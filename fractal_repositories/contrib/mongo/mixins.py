from datetime import datetime, timezone
from typing import Any, Iterator, Optional, Tuple

from fractal_specifications.contrib.mongo.specifications import (
    MongoSpecificationBuilder,
)
from fractal_specifications.generic.operators import EqualsSpecification
from fractal_specifications.generic.specification import Specification
from pymongo import MongoClient
from pymongo.database import Database
from pymongo.server_api import ServerApi

from fractal_repositories.core.repositories import EntityType, Repository
from fractal_repositories.utils.stored_specification import (
    to_native_datetime,
    to_stored_specification,
)


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

    #: Store datetimes as BSON dates rather than the ISO strings
    #: ``Entity.asdict()`` produces. Dates sort and compare correctly across
    #: offsets, and work with date indexes, TTL indexes and date aggregations.
    #: A collection written without it holds strings that datetime filters can
    #: no longer see, so it has to be migrated: see ``auto_migrate``.
    native_datetimes: bool = False
    #: With ``native_datetimes``, migrate this collection's string datetimes on
    #: first use (see :func:`~fractal_repositories.contrib.mongo.migrations.migrate_datetimes`).
    #: Runs once: completion is recorded, later starts only look that up. Turn
    #: it off to migrate from a deploy step instead, e.g. for a collection large
    #: enough that its first scan should not delay a request.
    auto_migrate: bool = True

    def __init__(
        self,
        collection: str = "",
        collection_prefix: str = "",
        *args,
        native_datetimes: Optional[bool] = None,
        auto_migrate: Optional[bool] = None,
        **kwargs,
    ):
        super().__init__(*args, **kwargs)
        if native_datetimes is not None:
            self.native_datetimes = native_datetimes
        if auto_migrate is not None:
            self.auto_migrate = auto_migrate
        self._migration_checked = False
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
        self._ensure_migrated()
        self.collection.insert_one(self._to_document(entity))
        return entity

    def update(self, entity: EntityType, *, upsert=False) -> EntityType:
        self._ensure_migrated()
        if obj := self.collection.find_one({"id": entity.id}):
            obj.update(self._to_document(entity))
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
            self._build(EqualsSpecification("id", entity.id) & expected),
            {"$set": self._to_document(entity)},
        )
        # matched, not modified: a swap that writes back an identical document
        # is still a swap this caller won, and modified_count would report 0.
        return result.matched_count == 1

    def remove_one(self, specification: Specification):
        self.collection.delete_one(self._build(specification))

    def find_one(self, specification: Specification) -> EntityType:
        for obj in self.collection.find(self._build(specification)):
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

        collection = self.collection.find(self._build(specification))

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
        return self.collection.count_documents(self._build(specification) or {})

    def is_healthy(self) -> bool:
        return bool(self.client.server_info().get("ok", False))

    def _build(self, specification: Optional[Specification]):
        # Documents hold entity.asdict(): datetimes, dates, decimals and the
        # like as strings. A filter has to carry them in that same shape, or
        # Mongo, which never compares across BSON types, matches nothing.
        self._ensure_migrated()
        return MongoSpecificationBuilder.build(
            to_stored_specification(
                specification, native_datetimes=self.native_datetimes
            )
        )

    def _to_document(self, entity: EntityType) -> dict:
        if not self.native_datetimes:
            return entity.asdict()
        return _native_datetimes(entity.asdict(skip_types=[datetime]))

    def _ensure_migrated(self):
        """Migrate this collection to native datetimes, once per process and
        once per collection: a recorded migration costs one lookup."""
        if self._migration_checked or not (self.native_datetimes and self.auto_migrate):
            return
        from fractal_repositories.contrib.mongo.migrations import (
            is_migrated,
            migrate_datetimes,
        )

        if not is_migrated(self):
            migrate_datetimes(self)
        self._migration_checked = True

    def _obj_to_domain(self, obj: dict) -> EntityType:
        # BSON dates are UTC by definition, but pymongo hands them back naive
        # unless the client was created with tz_aware=True.
        return self.entity.clean(**_utc_datetimes(obj))


def _native_datetimes(value: Any) -> Any:
    if isinstance(value, dict):
        return {k: _native_datetimes(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_native_datetimes(v) for v in value]
    if isinstance(value, datetime):
        return to_native_datetime(value)
    return value


def _utc_datetimes(value: Any) -> Any:
    if isinstance(value, dict):
        return {k: _utc_datetimes(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_utc_datetimes(v) for v in value]
    if isinstance(value, datetime) and value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value
