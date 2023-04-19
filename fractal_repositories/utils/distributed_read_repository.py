from dataclasses import dataclass
from typing import Callable, Iterator, List, Optional

from fractal_specifications.generic.specification import Specification

from fractal_repositories.core.repositories import EntityType, ReadRepository


@dataclass
class DistributedRelation:
    repository: ReadRepository
    specification_func: Callable[[EntityType], Specification]
    aggregate_target_field: str = ""


class DistributedReadRepository(ReadRepository[EntityType]):
    def __init__(
        self,
        *,
        main_repository: ReadRepository,
        other_repositories: List[DistributedRelation],
    ):
        super(DistributedReadRepository, self).__init__()
        self.main_repository: ReadRepository = main_repository
        self.other_repositories: List[DistributedRelation] = other_repositories

    def find_one(self, specification: Specification) -> EntityType:
        for entity in self.find(specification):
            return entity
        raise self._object_not_found()

    def find(
        self,
        specification: Optional[Specification] = None,
        *,
        offset: int = 0,
        limit: int = 0,
        order_by: str = "",
    ) -> Iterator[EntityType]:
        for main_entity in self.main_repository.find(
            specification, offset=offset, limit=limit, order_by=order_by
        ):
            data = self.entity.from_dict(main_entity.__dict__).asdict()
            for other_repository in self.other_repositories:
                for other_entity in other_repository.repository.find(
                    other_repository.specification_func(main_entity),
                ):
                    if other_repository.aggregate_target_field:
                        data[other_repository.aggregate_target_field].append(
                            other_entity
                        )
                    else:
                        data.update(
                            {
                                k: v
                                for k, v in other_entity.__dict__.items()
                                if v and k != "id"
                            }
                        )
            yield self.entity.from_dict(data)

    def is_healthy(self) -> bool:
        return self.main_repository.is_healthy() and all(
            map(lambda i: i.repository.is_healthy(), self.other_repositories)
        )
