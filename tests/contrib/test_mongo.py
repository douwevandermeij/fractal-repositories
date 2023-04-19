import uuid

import pytest


def get_obj(mongo_test_model):
    return mongo_test_model(
        id=str(uuid.uuid4()),
        name="name",
        description="description",
    )


def test_is_healthy(mongo_test_repository):
    assert mongo_test_repository.is_healthy()


def test_find(mongo_test_repository, mongo_test_model):
    obj1 = get_obj(mongo_test_model)
    obj2 = get_obj(mongo_test_model)
    obj1.id = "1"
    obj2.id = "2"
    mongo_test_repository.add(obj1)
    mongo_test_repository.add(obj2)

    assert len(list(mongo_test_repository.find())) == 2
    assert list(mongo_test_repository.find()) == [obj1, obj2]


def test_find_reverse(mongo_test_repository, mongo_test_model):
    obj1 = get_obj(mongo_test_model)
    obj2 = get_obj(mongo_test_model)
    obj1.id = "1"
    obj2.id = "2"
    mongo_test_repository.add(obj1)
    mongo_test_repository.add(obj2)

    assert len(list(mongo_test_repository.find(order_by="-id"))) == 2
    assert list(mongo_test_repository.find(order_by="-id")) == [obj2, obj1]


def test_find_offset_limit(mongo_test_repository, mongo_test_model):
    obj1 = get_obj(mongo_test_model)
    obj2 = get_obj(mongo_test_model)
    obj3 = get_obj(mongo_test_model)
    obj1.id = "1"
    obj2.id = "2"
    obj3.id = "3"
    mongo_test_repository.add(obj1)
    mongo_test_repository.add(obj2)
    mongo_test_repository.add(obj3)

    assert len(list(mongo_test_repository.find(offset=1, limit=1))) == 1
    assert list(mongo_test_repository.find(offset=1, limit=1)) == [obj2]


def test_find_filter(mongo_test_repository, mongo_test_model):
    obj1 = get_obj(mongo_test_model)
    obj2 = get_obj(mongo_test_model)
    mongo_test_repository.add(obj1)
    mongo_test_repository.add(obj2)

    from fractal_specifications.generic.specification import Specification

    assert len(list(mongo_test_repository.find(Specification.parse(id=obj1.id)))) == 1
    assert list(mongo_test_repository.find(Specification.parse(id=obj1.id))) == [obj1]


def test_find_one(mongo_test_repository, mongo_test_model):
    obj1 = get_obj(mongo_test_model)
    obj2 = get_obj(mongo_test_model)
    mongo_test_repository.add(obj1)
    mongo_test_repository.add(obj2)

    from fractal_specifications.generic.specification import Specification

    assert mongo_test_repository.find_one(Specification.parse(id=obj1.id)) == obj1


def test_find_one_error(mongo_test_repository, mongo_test_model):
    from fractal_specifications.generic.specification import Specification

    from fractal_repositories.exceptions import ObjectNotFoundException

    with pytest.raises(ObjectNotFoundException):
        mongo_test_repository.find_one(Specification.parse(id="1"))


def test_add(mongo_test_repository, mongo_test_model):
    obj = get_obj(mongo_test_model)
    mongo_test_repository.add(obj)

    assert len(list(mongo_test_repository.find())) == 1
    assert list(mongo_test_repository.find())[0] == obj


def test_update(mongo_test_repository, mongo_test_model):
    obj = get_obj(mongo_test_model)
    mongo_test_repository.add(obj)

    obj.name = "test"
    mongo_test_repository.update(obj)

    assert len(list(mongo_test_repository.find())) == 1
    assert list(mongo_test_repository.find())[0] == obj


def test_update_error(mongo_test_repository, mongo_test_model):
    obj = get_obj(mongo_test_model)

    from fractal_repositories.exceptions import ObjectNotFoundException

    with pytest.raises(ObjectNotFoundException):
        mongo_test_repository.update(obj)


def test_update_upsert(mongo_test_repository, mongo_test_model):
    obj = get_obj(mongo_test_model)
    mongo_test_repository.update(obj, upsert=True)

    assert len(list(mongo_test_repository.find())) == 1
    assert list(mongo_test_repository.find())[0] == obj


def test_remove_one(mongo_test_repository, mongo_test_model):
    obj = get_obj(mongo_test_model)
    mongo_test_repository.add(obj)

    from fractal_specifications.generic.specification import Specification

    mongo_test_repository.remove_one(Specification.parse(id=obj.id))

    assert len(list(mongo_test_repository.find())) == 0
