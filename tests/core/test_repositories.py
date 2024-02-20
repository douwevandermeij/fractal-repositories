import pytest
from fractal_specifications.generic.specification import Specification


def test_no_entity():
    from fractal_repositories.mixins.inmemory_repository_mixin import (
        InMemoryRepositoryMixin,
    )

    class TestRepository(InMemoryRepositoryMixin[type(...)]): ...

    from fractal_repositories.exceptions import RepositoryException

    with pytest.raises(RepositoryException):
        TestRepository()


def test_find_one_not_found(an_object):
    from fractal_repositories.exceptions import ObjectNotFoundException
    from fractal_repositories.mixins.inmemory_repository_mixin import (
        InMemoryRepositoryMixin,
    )

    class TestObjectNotFoundException(ObjectNotFoundException): ...

    class TestRepository(InMemoryRepositoryMixin[an_object.__class__]):
        entity = an_object.__class__
        object_not_found_exception_class = TestObjectNotFoundException

    with pytest.raises(TestObjectNotFoundException):
        TestRepository().find_one(Specification.parse(id="an_object.id"))
