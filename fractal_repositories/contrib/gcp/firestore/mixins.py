from typing import Iterable, Iterator, Optional, Union

from fractal_specifications.contrib.google_firestore.specifications import (
    FirestoreSpecificationBuilder,
)
from fractal_specifications.generic.specification import Specification
from google.cloud.firestore_v1 import Client, DocumentSnapshot, FieldFilter, Query
from google.cloud.firestore_v1.base_collection import BaseCollectionReference
from google.cloud.firestore_v1.base_query import BaseQuery

from fractal_repositories.core.repositories import EntityType, Repository


class FirestoreClient(object):
    instance = None

    def __new__(cls, *args, **kwargs):
        if not isinstance(cls.instance, cls):
            cls.instance = object.__new__(cls)
        return cls.instance

    def get_firestore_client(self):
        if not hasattr(self.instance, "firestore_client"):
            import firebase_admin  # type: ignore
            from firebase_admin import firestore

            cred = None
            if service_account_key := getattr(
                self.instance, "GCP_SERVICE_ACCOUNT_KEY", ""
            ):
                from firebase_admin import credentials

                cred = credentials.Certificate(service_account_key)

            firebase_admin.initialize_app(cred)
            self.instance.firestore_client = firestore.client()
            if hasattr(self.instance.firestore_client, "_firestore_api"):
                self._firestore_api_internal = (
                    self.instance.firestore_client._firestore_api
                )  # trigger creation of a gRPC channel (singleton)
        return self.instance.firestore_client


class AttrDict(dict):
    """
    Access dictionaries as objects
    """

    def __init__(self, *args, **kwargs):
        super(AttrDict, self).__init__(*args, **kwargs)
        self.__dict__ = self


class FirestoreRepositoryMixin(Repository[EntityType]):
    """
    https://github.com/GoogleCloudPlatform/python-docs-samples/blob/46fa5a588858021ea32350584a4ee178cd7c1f33/firestore/cloud-client/snippets.py#L62-L66
    """

    def __init__(self, collection: str = "", *, collection_prefix: str = "", **kwargs):
        super(FirestoreRepositoryMixin, self).__init__(
            collection=collection, collection_prefix=collection_prefix, **kwargs
        )

        client: Client = FirestoreClient().get_firestore_client()
        if not collection and self.entity:
            collection = self.entity.__name__  # type: ignore
        if collection_prefix:
            collection = "-".join([collection_prefix, collection])
        self.collection = client.collection(collection.lower().replace(" ", "-"))

    def add(self, entity: EntityType) -> EntityType:
        doc_ref = self.collection.document(entity.id)
        doc_ref.set(entity.asdict())
        return entity

    def update(self, entity: EntityType, *, upsert=False) -> EntityType:
        doc_ref = self.collection.document(entity.id)
        doc = doc_ref.get()
        if doc.exists:
            doc_ref.set(entity.asdict())
            return entity
        elif upsert:
            return self.add(entity)
        raise self._object_not_found()

    def remove_one(self, specification: Specification):
        if entity := self.find_one(specification):
            self.collection.document(entity.id).delete()

    @staticmethod
    def _get_collection_stream(collection) -> Iterable[DocumentSnapshot]:
        for i in collection.stream():
            yield i

    def find_one(self, specification: Specification) -> EntityType:
        _filter = FirestoreSpecificationBuilder.build(specification)
        collection: Union[BaseCollectionReference, BaseQuery] = self.collection
        if _filter:
            if isinstance(_filter, list):
                for f in _filter:
                    collection = collection.where(filter=FieldFilter(*f))
            else:
                collection = collection.where(filter=FieldFilter(*_filter))

        def _spec_filter(i: DocumentSnapshot):
            if data := i.to_dict():
                return specification.is_satisfied_by(AttrDict(**data))

        for doc in filter(
            _spec_filter,
            self._get_collection_stream(collection),
        ):
            return self.entity.from_dict(doc.to_dict())
        raise self._object_not_found()

    def find(
        self,
        specification: Optional[Specification] = None,
        *,
        offset: int = 0,
        limit: int = 0,
        order_by: str = "",
    ) -> Iterator[EntityType]:
        _filter = FirestoreSpecificationBuilder.build(specification)
        direction = Query.ASCENDING
        order_by = order_by or self.order_by
        if order_by.startswith("-"):
            order_by = order_by[1:]
            direction = Query.DESCENDING
        collection: Union[BaseCollectionReference, BaseQuery] = self.collection
        if _filter:
            if isinstance(_filter, list):
                for f in _filter:
                    collection = collection.where(filter=FieldFilter(*f))
            else:
                collection = collection.where(filter=FieldFilter(*_filter))

        if order_by:
            collection = collection.order_by(order_by, direction=direction)

        if limit:
            if offset and (last := list(collection.limit(offset).stream())[-1]):
                collection = collection.start_after(
                    {order_by: (last.to_dict() or {}).get(order_by)}
                ).limit(limit)
            else:
                collection = collection.limit(limit)
        for doc in self._get_collection_stream(collection):
            yield self.entity.from_dict(doc.to_dict())

    def is_healthy(self) -> bool:
        return True
