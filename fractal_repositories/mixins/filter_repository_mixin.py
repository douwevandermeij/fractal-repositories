from abc import ABC
from copy import deepcopy
from typing import Callable, Generic, Iterator, Optional

from fractal_specifications.generic.specification import Specification

from fractal_repositories.core.repositories import EntityType, Repository


class FilterRepositoryMixin(Repository[EntityType], Generic[EntityType], ABC):
    def find_filter(
        self,
        sub_specification: Specification,
        *,
        pre_processor: Optional[Callable[[EntityType], EntityType]] = None,
        specification: Optional[Specification] = None,
        offset: int = 0,
        limit: int = 0,
        order_by: str = "id",
    ) -> Iterator[EntityType]:
        entities = self.find(
            specification, offset=offset, limit=limit, order_by=order_by
        )
        return filter(
            lambda e: sub_specification.is_satisfied_by(
                pre_processor(deepcopy(e)) if pre_processor else e
            ),
            entities,
        )
