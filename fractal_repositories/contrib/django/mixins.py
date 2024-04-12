from dataclasses import asdict
from typing import Dict, Generator, Optional, Type

from django.db.models import ForeignKey, Model  # type: ignore
from fractal_specifications.contrib.django.specifications import (
    DjangoOrmSpecificationBuilder,
)
from fractal_specifications.generic.specification import Specification

from fractal_repositories.core.repositories import EntityType, Repository


class DjangoModelRepositoryMixin(Repository[EntityType]):
    def __init__(self, django_model: Type[Model], *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.django_model = django_model

    def add(self, entity: EntityType) -> EntityType:
        direct_data, related_data = self.__get_direct_related_data(entity)
        obj = self.django_model.objects.create(**direct_data)
        entity.id = obj.id
        return entity

    def update(self, entity: EntityType, *, upsert=False) -> EntityType:
        if _entity := self.django_model.objects.filter(pk=entity.id):
            direct_data, related_data = self.__get_direct_related_data(entity)
            _entity.update(**direct_data)
            return self._obj_to_domain(
                self.django_model.objects.get(pk=entity.id).__dict__
            )
        elif upsert:
            return self.add(entity)
        raise self._object_not_found()

    def __get_direct_related_data(self, entity: EntityType):
        direct_data = {}
        related_data = {}

        def field_name(field):
            if type(field) is ForeignKey:
                return field.name + "_id"
            return field.name

        direct_fields = [field_name(f) for f in self.django_model._meta.fields]
        for k, v in asdict(entity).items():
            if type(v) is list:
                related_data[k] = v
            else:
                if k in direct_fields:
                    direct_data[k] = v
        return direct_data, related_data

    def __get_obj(self, specification: Specification):
        _filter = DjangoOrmSpecificationBuilder.build(specification)
        try:
            obj = self.django_model.objects.get(_filter)
        except self.django_model.DoesNotExist:
            raise self._object_not_found()
        return obj

    def remove_one(self, specification: Specification):
        self.__get_obj(specification).delete()

    def find_one(self, specification: Specification) -> EntityType:
        return self._obj_to_domain(self.__get_obj(specification).__dict__)

    def find(
        self,
        specification: Optional[Specification] = None,
        *,
        offset: int = 0,
        limit: int = 0,
        order_by: str = "",
    ) -> Generator[EntityType, None, None]:
        if _filter := DjangoOrmSpecificationBuilder.build(specification):
            queryset = self.django_model.objects.filter(_filter)
        else:
            queryset = self.django_model.objects.all()

        order_by = order_by or self.order_by
        if order_by:
            queryset = queryset.order_by(order_by)

        if limit:
            queryset = queryset[offset : offset + limit]

        for obj in queryset:
            yield self._obj_to_domain(obj.__dict__)

    def is_healthy(self) -> bool:
        return True

    def _obj_to_domain(self, obj: Dict) -> EntityType:
        return self.entity.clean(**obj)
