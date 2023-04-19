import pytest

from tests.fixtures import A, B


def test_is_healthy(distributed_abc_inmemory_read_repository):
    assert distributed_abc_inmemory_read_repository.is_healthy()


def test_find_one(
    inmemory_a_repository,
    inmemory_b_repository,
    distributed_abc_inmemory_read_repository,
):
    inmemory_a_repository.add(A(1, "a"))
    inmemory_a_repository.add(A(2, "b"))

    inmemory_b_repository.add(B(3, 1))
    inmemory_b_repository.add(B(4, 2))

    from fractal_specifications.generic.specification import Specification

    assert distributed_abc_inmemory_read_repository.find_one(
        Specification.parse(id=1)
    ).asdict() == {"id": 1, "name": "a", "number": 1, "extra": ""}


def test_find_one_error(
    inmemory_a_repository,
    inmemory_b_repository,
    distributed_abc_inmemory_read_repository,
):
    from fractal_specifications.generic.specification import Specification

    from fractal_repositories.exceptions import ObjectNotFoundException

    with pytest.raises(ObjectNotFoundException):
        distributed_abc_inmemory_read_repository.find_one(Specification.parse(id=1))


def test_find(
    inmemory_a_repository,
    inmemory_b_repository,
    distributed_abc_inmemory_read_repository,
):
    inmemory_a_repository.add(A(1, "a"))
    inmemory_a_repository.add(A(2, "b"))
    inmemory_a_repository.add(A(3, "c"))

    inmemory_b_repository.add(B(4, 1))
    inmemory_b_repository.add(B(5, 1, "d"))
    inmemory_b_repository.add(B(6, 2))

    assert [i.asdict() for i in distributed_abc_inmemory_read_repository.find()] == [
        {"id": 1, "name": "a", "number": 1, "extra": "d"},
        {"id": 2, "name": "b", "number": 2, "extra": ""},
        {"id": 3, "name": "c", "number": 0, "extra": ""},
    ]


def test_find_aggregate(
    inmemory_a_repository,
    inmemory_b_repository,
    distributed_abd_inmemory_read_repository,
):
    inmemory_a_repository.add(A(1, "a"))
    inmemory_a_repository.add(A(2, "b"))

    inmemory_b_repository.add(B(3, 1, "c"))
    inmemory_b_repository.add(B(4, 1, "d"))

    from tests.fixtures import D

    assert list(distributed_abd_inmemory_read_repository.find()) == [
        D(
            id=1,
            name="a",
            bs=[
                B(id=3, number=1, extra="c"),
                B(id=4, number=1, extra="d"),
            ],
        ),
        D(id=2, name="b", bs=[]),
    ]
