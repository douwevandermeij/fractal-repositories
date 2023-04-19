import pytest

from tests.fixtures import A, B, C


def test_is_healthy(cached_inmemory_c_repository):
    assert cached_inmemory_c_repository.is_healthy()


def test_add(
    inmemory_c_repository, another_inmemory_c_repository, cached_inmemory_c_repository
):
    cached_inmemory_c_repository.add(C(1, "a", 1))

    assert len(inmemory_c_repository.entities) == 1
    assert len(another_inmemory_c_repository.entities) == 1


def test_update(
    inmemory_c_repository, another_inmemory_c_repository, cached_inmemory_c_repository
):
    cached_inmemory_c_repository.add(C(1, "a", 1))
    cached_inmemory_c_repository.update(C(1, "b", 1))

    assert inmemory_c_repository.entities[1].name == "b"
    assert another_inmemory_c_repository.entities[1].name == "b"


def test_remove_one(
    inmemory_c_repository, another_inmemory_c_repository, cached_inmemory_c_repository
):
    cached_inmemory_c_repository.add(C(1, "a", 1))

    from fractal_specifications.generic.specification import Specification

    cached_inmemory_c_repository.remove_one(Specification.parse(id=1))

    assert len(inmemory_c_repository.entities) == 0
    assert len(another_inmemory_c_repository.entities) == 0


def test_find(
    inmemory_c_repository, another_inmemory_c_repository, cached_inmemory_c_repository
):
    cached_inmemory_c_repository.add(C(1, "a", 1))
    cached_inmemory_c_repository.add(C(2, "b", 2))

    from fractal_specifications.generic.specification import Specification

    assert [
        e.asdict() for e in cached_inmemory_c_repository.find(Specification.parse(id=1))
    ] == [
        {"id": 1, "name": "a", "number": 1, "extra": ""},
    ]


def test_find_one_error(
    inmemory_c_repository, another_inmemory_c_repository, cached_inmemory_c_repository
):
    from fractal_specifications.generic.specification import Specification

    from fractal_repositories.exceptions import ObjectNotFoundException

    with pytest.raises(ObjectNotFoundException):
        cached_inmemory_c_repository.find_one(Specification.parse(id=1))


def test_find_one(
    inmemory_c_repository, another_inmemory_c_repository, cached_inmemory_c_repository
):
    cached_inmemory_c_repository.add(C(1, "a", 1))
    cached_inmemory_c_repository.add(C(2, "b", 2))

    from fractal_specifications.generic.specification import Specification

    assert cached_inmemory_c_repository.find_one(
        Specification.parse(id=1)
    ).asdict() == {"id": 1, "name": "a", "number": 1, "extra": ""}


def test_load_cache(
    inmemory_c_repository, another_inmemory_c_repository, cached_inmemory_c_repository
):
    inmemory_c_repository.add(C(1, "a", 1))

    assert len(another_inmemory_c_repository.entities) == 0

    cached_inmemory_c_repository.load_cache()

    assert len(list(cached_inmemory_c_repository.find())) == 1


def test_reload_cache(
    inmemory_c_repository, another_inmemory_c_repository, cached_inmemory_c_repository
):
    inmemory_c_repository.add(C(1, "a", 1))
    inmemory_c_repository.add(C(2, "b", 2))

    cached_inmemory_c_repository.load_cache()

    assert len(another_inmemory_c_repository.entities) == 2

    from fractal_specifications.generic.specification import Specification

    inmemory_c_repository.remove_one(Specification.parse(id=2))
    inmemory_c_repository.add(C(3, "c", 3))

    cached_inmemory_c_repository.reload_cache()

    assert [e.id for e in cached_inmemory_c_repository.find()] == [1, 3]


def test_cached_distributed_inmemory_read_repository(
    inmemory_a_repository,
    inmemory_b_repository,
    cached_distributed_inmemory_read_repository,
):
    inmemory_a_repository.add(A(1, "a"))
    inmemory_a_repository.add(A(2, "b"))

    inmemory_b_repository.add(B(1, 1))
    inmemory_b_repository.add(B(2, 2))

    cached_distributed_inmemory_read_repository.load_cache()

    assert [e.asdict() for e in cached_distributed_inmemory_read_repository.find()] == [
        {"id": 1, "name": "a", "number": 1, "extra": ""},
        {"id": 2, "name": "b", "number": 2, "extra": ""},
    ]
