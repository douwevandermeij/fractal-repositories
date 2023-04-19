import json
from dataclasses import dataclass
from typing import List

import pytest
from fractal_specifications.generic.specification import Specification

from fractal_repositories.core.entity import Entity


@dataclass
class AnObject(Entity):
    id: str
    name: str = "default_name"


@dataclass
class A(Entity):
    id: int
    name: str


@dataclass
class B(Entity):
    id: int
    number: int
    extra: str = ""


@dataclass
class C(Entity):
    id: int
    name: str
    number: int = 0
    extra: str = ""


@dataclass
class D(Entity):
    id: int
    name: str
    bs: List[B] = None  # type: ignore

    def __post_init__(self):
        if not self.bs:
            self.bs = []


@pytest.fixture
def an_object():
    return AnObject("1")


@pytest.fixture
def another_object():
    return AnObject("2", "another_name")


@pytest.fixture
def inmemory_repository():
    from fractal_repositories.mixins.inmemory_repository_mixin import (
        InMemoryRepositoryMixin,
    )

    class InMemoryRepository(InMemoryRepositoryMixin[AnObject]):
        entity = AnObject

    return InMemoryRepository()


@pytest.fixture
def inmemory_a_repository():
    from fractal_repositories.mixins.inmemory_repository_mixin import (
        InMemoryRepositoryMixin,
    )

    class InMemoryARepository(InMemoryRepositoryMixin[A]):
        entity = A

    return InMemoryARepository()


@pytest.fixture
def inmemory_b_repository():
    from fractal_repositories.mixins.inmemory_repository_mixin import (
        InMemoryRepositoryMixin,
    )

    class InMemoryBRepository(InMemoryRepositoryMixin[B]):
        entity = B

    return InMemoryBRepository()


@pytest.fixture
def inmemory_c_repository():
    from fractal_repositories.mixins.inmemory_repository_mixin import (
        InMemoryRepositoryMixin,
    )

    class InMemoryCRepository(InMemoryRepositoryMixin[C]):
        entity = C

    return InMemoryCRepository()


@pytest.fixture
def another_inmemory_c_repository():
    from fractal_repositories.mixins.inmemory_repository_mixin import (
        InMemoryRepositoryMixin,
    )

    class InMemoryCRepository(InMemoryRepositoryMixin[C]):
        entity = C

    return InMemoryCRepository()


@pytest.fixture
def inmemory_filter_repository():
    from fractal_repositories.mixins.filter_repository_mixin import (
        FilterRepositoryMixin,
    )
    from fractal_repositories.mixins.inmemory_repository_mixin import (
        InMemoryRepositoryMixin,
    )

    class InMemoryFilterRepository(
        InMemoryRepositoryMixin[AnObject], FilterRepositoryMixin[AnObject]
    ):
        entity = AnObject

    return InMemoryFilterRepository()


@pytest.fixture
def external_data_inmemory_repository():
    from fractal_repositories.mixins.external_data_inmemory_repository_mixin import (
        ExternalDataInMemoryRepositoryMixin,
    )

    class ExternalDataInMemoryRepository(ExternalDataInMemoryRepositoryMixin[AnObject]):
        entity = AnObject

    return ExternalDataInMemoryRepository(AnObject)


@pytest.fixture
def distributed_abc_inmemory_read_repository(
    inmemory_a_repository, inmemory_b_repository
):
    from fractal_repositories.utils.distributed_read_repository import (
        DistributedReadRepository,
        DistributedRelation,
    )

    class DistributedCReadRepository(DistributedReadRepository[C]):
        entity = C

    return DistributedCReadRepository(
        main_repository=inmemory_a_repository,
        other_repositories=[
            DistributedRelation(
                inmemory_b_repository,
                lambda entity: Specification.parse(number=entity.id),
            )
        ],
    )


@pytest.fixture
def distributed_abd_inmemory_read_repository(
    inmemory_a_repository, inmemory_b_repository
):
    from fractal_repositories.utils.distributed_read_repository import (
        DistributedReadRepository,
        DistributedRelation,
    )

    class DistributedDReadRepository(DistributedReadRepository[D]):
        entity = D

    return DistributedDReadRepository(
        main_repository=inmemory_a_repository,
        other_repositories=[
            DistributedRelation(
                inmemory_b_repository,
                lambda entity: Specification.parse(number=entity.id),
                aggregate_target_field="bs",
            )
        ],
    )


@pytest.fixture
def cached_inmemory_c_repository(inmemory_c_repository, another_inmemory_c_repository):
    from fractal_repositories.utils.cached_repository import CachedRepository

    class CachedCRepository(CachedRepository[C]):
        entity = C

    cr = CachedCRepository(
        main_repository=inmemory_c_repository,
        cache_repository=another_inmemory_c_repository,
    )
    cr.load_cache()

    return cr


@pytest.fixture
def cached_distributed_inmemory_read_repository(
    distributed_abc_inmemory_read_repository, inmemory_c_repository
):
    from fractal_repositories.utils.cached_repository import CachedRepository

    class CachedCRepository(CachedRepository[C]):
        entity = C

    cr = CachedCRepository(
        main_repository=distributed_abc_inmemory_read_repository,
        cache_repository=inmemory_c_repository,
    )
    cr.load_cache()

    return cr


@pytest.fixture
def mocker_os_path_exists(mocker):
    mocker.patch("os.path.exists", lambda s: True)


@pytest.fixture
def mocker_os_path_exists_error(mocker):
    mocker.patch("os.path.exists", lambda s: False)


@pytest.fixture
def mocker_os_remove(mocker):
    mocker.patch("os.remove", lambda s: True)


@pytest.fixture
def mocker_os_remove_error(mocker):
    def wrapper(s):
        raise FileNotFoundError

    mocker.patch("os.remove", wrapper)


@pytest.fixture
def mocker_file_open_data(mocker, mocker_os_path_exists):
    def wrapper(value):
        data = (
            value
            if type(value) == str
            else "\n".join([json.dumps(e.asdict()) for e in value])
        )
        mocked_data = mocker.mock_open(read_data=data)
        mocker.patch("builtins.open", mocked_data)

    wrapper([])
    return wrapper


@pytest.fixture
def file_repository(mocker_file_open_data):
    from fractal_repositories.mixins.file_repository_mixin import FileRepositoryMixin

    class FileRepository(FileRepositoryMixin[AnObject]):
        entity = AnObject

    return FileRepository(root_dir="")


@pytest.fixture
def inmemory_file_repository():
    from fractal_repositories.mixins.inmemory_repository_mixin import (
        InMemoryFileRepositoryMixin,
    )

    return InMemoryFileRepositoryMixin()


@pytest.fixture
def file_file_repository(mocker_file_open_data):
    from fractal_repositories.mixins.file_repository_mixin import (
        FileFileRepositoryMixin,
    )

    return FileFileRepositoryMixin(root_dir="")
