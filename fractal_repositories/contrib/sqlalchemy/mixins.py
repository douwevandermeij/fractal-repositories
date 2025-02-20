from __future__ import annotations

import dataclasses
import logging
from abc import ABC, abstractmethod
from typing import (
    Dict,
    Generator,
    Generic,
    List,
    Optional,
    Type,
    TypeVar,
    get_type_hints,
)

from fractal_specifications.contrib.sqlalchemy.specifications import (
    SqlAlchemyOrmSpecificationBuilder,
)
from fractal_specifications.generic.operators import EqualsSpecification
from fractal_specifications.generic.specification import Specification
from sqlalchemy import MetaData, Table, create_engine  # type: ignore
from sqlalchemy.engine import Engine  # type: ignore
from sqlalchemy.exc import ArgumentError, DBAPIError  # type: ignore
from sqlalchemy.orm import Mapper, Session, sessionmaker  # type: ignore
from sqlalchemy.sql.elements import BooleanClauseList  # type: ignore

from fractal_repositories.core.repositories import Entity, EntityType, Repository
from fractal_repositories.exceptions import ObjectNotFoundException


class UnknownListItemTypeException(Exception):
    code = "UNKNOWN_LIST_ITEM_TYPE_EXCEPTION"


class SqlAlchemyException(Exception):
    code = "SQLALCHEMY_EXCEPTION"


class SqlAlchemyDao(ABC):
    @staticmethod
    @abstractmethod
    def mapper(meta: MetaData, foreign_keys: Dict[str, Mapper]) -> Mapper:
        raise NotImplementedError

    @staticmethod
    @abstractmethod
    def table(meta: MetaData) -> Table:
        raise NotImplementedError

    @staticmethod
    def from_domain(obj: Entity) -> SqlAlchemyDao:
        raise NotImplementedError


EntityDao = TypeVar("EntityDao", bound=SqlAlchemyDao)


class DaoMapper(ABC):
    instance = None

    def __new__(cls, *args, **kwargs):
        if not isinstance(cls.instance, cls):
            cls.instance = object.__new__(cls)
            cls.instance.done = False
        return cls.instance

    def start_mappers(self, engine: Engine):
        if not self.done:
            meta = MetaData()
            self.application_mappers(meta)
            meta.create_all(engine)
            self.done: bool = True

    @abstractmethod
    def application_mappers(self, meta: MetaData):
        raise NotImplementedError


class AbstractUnitOfWork(ABC):
    def __enter__(self) -> AbstractUnitOfWork:
        return self

    def __exit__(self, *args):
        self.rollback()

    @abstractmethod
    def commit(self):
        raise NotImplementedError

    @abstractmethod
    def rollback(self):
        raise NotImplementedError


class SqlAlchemyUnitOfWork(AbstractUnitOfWork):
    session_factory: sessionmaker

    def __enter__(self) -> AbstractUnitOfWork:
        self.session: Session = self.session_factory()
        return super().__enter__()

    def __exit__(self, *args):
        super().__exit__(*args)
        self.session.close()

    def commit(self):
        self.session.commit()

    def rollback(self):
        self.session.rollback()


class SqlAlchemyRepositoryMixin(
    Generic[EntityType, EntityDao], Repository[EntityType], SqlAlchemyUnitOfWork
):
    entity: EntityType
    entity_dao: EntityDao
    application_mapper: Type[DaoMapper]

    def __init__(self, connection_str: str, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.connection_str = connection_str
        engine = create_engine(
            self.connection_str,
        )

        self.application_mapper().start_mappers(engine)

        self.session_factory = sessionmaker(
            bind=engine,
            expire_on_commit=False,
        )

    def add(self, entity: EntityType) -> EntityType:
        return self.__add(entity, self.entity_dao)

    def __add(self, entity: EntityType, entity_dao_class: EntityDao) -> EntityType:
        entity_dao = entity_dao_class.from_domain(entity)
        with self:
            try:
                self.session.add(entity_dao)
                self.commit()
            except DBAPIError as e:
                raise SqlAlchemyException(e)
        return entity

    def update(self, entity: EntityType, *, upsert=False) -> EntityType:
        return self.__update(entity, self.entity_dao, upsert=upsert)

    def __update(
        self, entity: EntityType, entity_dao_class: EntityDao, *, upsert=False
    ) -> EntityType:
        """Recursive function"""
        with self:
            try:
                existing_entity_dao = self._find_one_raw(
                    EqualsSpecification("id", entity.id),
                    entity_dao_class=entity_dao_class,
                )
            except ObjectNotFoundException:
                existing_entity_dao = None
            except ArgumentError:  # Python 3.8 error
                raise UnknownListItemTypeException(
                    f"DAO '{entity_dao_class}' has an unknown list collection DAO, please add the type for the list."
                )
            if existing_entity_dao:
                try:
                    self.__update_existing_record(
                        entity, entity_dao_class, existing_entity_dao
                    )
                except DBAPIError as e:
                    raise SqlAlchemyException(e)
                except AttributeError:  # Python >= 3.9 error
                    raise UnknownListItemTypeException(
                        f"DAO '{entity_dao_class}' has an unknown list collection DAO, please add the type for the list."
                    )
                return entity
            elif upsert:
                return self.__add(entity, entity_dao_class)
        raise self._object_not_found()

    def __update_existing_record(self, entity, entity_dao_class, existing_entity_dao):
        updating_entity_dao = entity_dao_class.from_domain(entity)
        regular_fields = []
        list_fields = []

        for k, v in entity_dao_class.__annotations__.items():
            if hasattr(v, "__origin__") and v.__origin__ is list:
                list_fields.append(k)
            else:
                regular_fields.append(k)

        self.__update_main_entity(
            existing_entity_dao, regular_fields, updating_entity_dao
        )
        self.__update_compound_entities(entity, entity_dao_class, list_fields)
        self.commit()

    def __update_main_entity(
        self, existing_entity_dao, regular_fields, updating_entity_dao
    ):
        for k, v in updating_entity_dao.__dict__.items():
            if hasattr(existing_entity_dao, k) and k in regular_fields:
                setattr(existing_entity_dao, k, v)

    def __update_compound_entities(self, entity, entity_dao_class, list_fields):
        for field in list_fields:
            item_dao_class = get_type_hints(entity_dao_class)[field].__args__[0]

            # check for new items
            for item in getattr(entity, field):
                self.__update(item, item_dao_class, upsert=True)

            # check for items to delete
            foreign_key = getattr(entity_dao_class, field).expression.right
            items = list(
                self.session.query(item_dao_class).filter(foreign_key == entity.id)
            )
            item_ids = [item.id for item in getattr(entity, field)]
            for item_dao in items:
                if item_dao.id not in item_ids:
                    self.session.delete(item_dao)

    def remove_one(self, specification: Specification):
        entity = self._find_one_raw(specification)
        if entity:
            self.session.delete(entity)
            self.commit()

    def find_one(self, specification: Specification) -> EntityType:
        try:
            entity = self._find_one_raw(specification)
        except ObjectNotFoundException:
            raise
        return self._dao_to_domain(entity)

    def find(
        self,
        specification: Optional[Specification] = None,
        *,
        offset: int = 0,
        limit: int = 0,
        order_by: str = "",
    ) -> Generator[EntityType, None, None]:
        order_by = order_by or self.order_by
        entities = self._find_raw(
            specification=specification,
            offset=offset,
            limit=limit,
            order_by=order_by,
        )

        for entity in entities:
            yield self._dao_to_domain(entity)

    def _dao_to_domain(self, entity: EntityType) -> EntityType:
        return self.__dao_to_domain(entity, self.entity, self.entity_dao)

    def __dao_to_domain(
        self, entity: EntityType, domain_model: EntityType, entity_dao: EntityDao
    ) -> EntityType:
        """Recursive function"""
        list_fields = []
        for k, v in entity_dao.__annotations__.items():
            if hasattr(v, "__origin__") and v.__origin__ is list:
                list_fields.append(k)
        d = entity.__dict__
        for field in list_fields:
            if hasattr(entity, field):
                item_domain_model = get_type_hints(domain_model)[field].__args__[0]
                item_entity_dao = get_type_hints(entity_dao)[field].__args__[0]
                d[field] = [
                    self.__dao_to_domain(sub_entity, item_domain_model, item_entity_dao)
                    for sub_entity in getattr(entity, field)
                ]
        fields = set(f.name for f in dataclasses.fields(domain_model))
        return domain_model.from_dict({k: v for k, v in d.items() if k in fields})

    def _find_one_raw(
        self,
        specification: Specification,
        *,
        entity_dao_class: Optional[EntityDao] = None,
    ) -> EntityType:
        entities = self._find_raw(specification, entity_dao_class=entity_dao_class)

        for entity in filter(lambda i: specification.is_satisfied_by(i), entities):
            return entity
        raise self._object_not_found()

    def _find_raw(
        self,
        specification: Optional[Specification],
        *,
        entity_dao_class: Optional[EntityDao] = None,
        offset: int = 0,
        limit: int = 0,
        order_by: str = "",
    ) -> List[EntityType]:
        filters = None
        _filter = None
        if specification:
            _filter = SqlAlchemyOrmSpecificationBuilder.build(specification)
        if isinstance(_filter, list):
            filters = {}
            for f in _filter:
                filters.update(f)
            from sqlalchemy import or_

            # TODO move to SqlAlchemyOrmSpecificationBuilder
            filters = or_(
                *[
                    getattr(entity_dao_class or self.entity_dao, k) == v
                    for k, v in filters.items()
                ]
            )
        elif isinstance(_filter, dict):
            from sqlalchemy import and_

            if len(_filter) > 1:
                # TODO move to SqlAlchemyOrmSpecificationBuilder
                filters = and_(
                    *[
                        getattr(entity_dao_class or self.entity_dao, k) == v
                        for k, v in _filter.items()
                    ]
                )
            else:
                filters = _filter

        with self:
            ret = self.session.query(entity_dao_class or self.entity_dao)
        if type(filters) is dict:
            ret = ret.filter_by(**filters)
        if type(filters) is BooleanClauseList:
            ret = ret.where(filters)

        if order_by:
            if order_by.startswith("-"):
                _order_by = getattr(entity_dao_class or self.entity_dao, order_by[1:])
                desc = True
            else:
                _order_by = getattr(entity_dao_class or self.entity_dao, order_by)
                desc = False
            ret = ret.order_by(_order_by.desc() if desc else _order_by)

        if limit:
            ret = ret.offset(offset)
            ret = ret.limit(limit)
            return ret
        return ret

    def count(self, specification: Optional[Specification] = None) -> int:
        return self.session.query(self.entity_dao).count()

    def is_healthy(self) -> bool:
        try:
            with self:
                self.session.execute("SELECT 1")
        except Exception as e:
            logging.exception(f"Database is unhealthy! {e}")
            return False
        return True
