import pytest


def test_is_healthy(inmemory_repository):
    assert inmemory_repository.is_healthy()


def test_add(inmemory_repository, an_object):
    inmemory_repository.add(an_object)

    assert len(inmemory_repository.entities) == 1
    assert list(inmemory_repository.entities.values())[0] == an_object


def test_update(inmemory_repository, an_object):
    inmemory_repository.add(an_object)

    assert list(inmemory_repository.entities.values())[0].name != "update"

    an_object.name = "update"
    inmemory_repository.update(an_object)

    assert len(inmemory_repository.entities) == 1
    assert list(inmemory_repository.entities.values())[0].name == "update"


def test_update_upsert(inmemory_repository, an_object):
    inmemory_repository.update(an_object, upsert=True)

    assert len(inmemory_repository.entities) == 1
    assert list(inmemory_repository.entities.values())[0] == an_object


def test_update_upsert_ignore(inmemory_repository, an_object):
    from fractal_repositories.exceptions import ObjectNotFoundException

    with pytest.raises(ObjectNotFoundException):
        inmemory_repository.update(an_object)

    assert len(inmemory_repository.entities) == 0


def test_remove_one(inmemory_repository, an_object):
    inmemory_repository.add(an_object)

    from fractal_specifications.generic.specification import Specification

    inmemory_repository.remove_one(Specification.parse(id=an_object.id))

    assert len(inmemory_repository.entities) == 0


def test_find_one(inmemory_repository, an_object):
    inmemory_repository.add(an_object)

    from fractal_specifications.generic.specification import Specification

    assert (
        inmemory_repository.find_one(Specification.parse(id=an_object.id)) == an_object
    )


def test_find(inmemory_repository, an_object):
    inmemory_repository.add(an_object)

    assert len(list(inmemory_repository.find())) == 1


def test_find_reverse(inmemory_repository, an_object, another_object):
    inmemory_repository.add(an_object)
    inmemory_repository.add(another_object)

    assert [i.id for i in inmemory_repository.find(order_by="id")] == [
        an_object.id,
        another_object.id,
    ]
    assert [i.id for i in inmemory_repository.find(order_by="-id")] == [
        another_object.id,
        an_object.id,
    ]


def test_find_reverse_default_reverse(inmemory_repository, an_object, another_object):
    inmemory_repository.add(an_object)
    inmemory_repository.add(another_object)

    inmemory_repository.order_by = "-id"
    assert [i.id for i in inmemory_repository.find()] == [
        another_object.id,
        an_object.id,
    ]


def test_find_limit(inmemory_repository, an_object, another_object):
    inmemory_repository.add(an_object)
    inmemory_repository.add(another_object)

    assert len(list(inmemory_repository.find())) == 2
    assert len(list(inmemory_repository.find(limit=1))) == 1


def test_find_with_specification(inmemory_repository, an_object):
    inmemory_repository.add(an_object)

    from fractal_specifications.generic.specification import Specification

    assert (
        len(list(inmemory_repository.find(Specification.parse(id=an_object.id)))) == 1
    )


def test_find_with_specification_empty(inmemory_repository, an_object):
    inmemory_repository.add(an_object)

    from fractal_specifications.generic.specification import Specification

    assert len(list(inmemory_repository.find(Specification.parse(id=2)))) == 0
