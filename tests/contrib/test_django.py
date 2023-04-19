import uuid

import pytest


def get_obj(django_test_model):
    return django_test_model(
        id=str(uuid.uuid4()),
        name="name",
        description="description",
    )


def test_is_healthy(django_test_repository):
    assert django_test_repository.is_healthy()


def test_find(django_test_repository, django_test_model):
    obj1 = get_obj(django_test_model)
    obj2 = get_obj(django_test_model)
    obj1.id = "1"
    obj2.id = "2"
    django_test_repository.add(obj1)
    django_test_repository.add(obj2)

    assert len(list(django_test_repository.find())) == 2
    assert list(django_test_repository.find()) == [obj1, obj2]


def test_find_reverse(django_test_repository, django_test_model):
    obj1 = get_obj(django_test_model)
    obj2 = get_obj(django_test_model)
    obj1.id = "1"
    obj2.id = "2"
    django_test_repository.add(obj1)
    django_test_repository.add(obj2)

    assert len(list(django_test_repository.find(order_by="-id"))) == 2
    assert list(django_test_repository.find(order_by="-id")) == [obj2, obj1]


def test_find_offset_limit(django_test_repository, django_test_model):
    obj1 = get_obj(django_test_model)
    obj2 = get_obj(django_test_model)
    obj3 = get_obj(django_test_model)
    obj1.id = "1"
    obj2.id = "2"
    obj3.id = "3"
    django_test_repository.add(obj1)
    django_test_repository.add(obj2)
    django_test_repository.add(obj3)

    assert len(list(django_test_repository.find(offset=1, limit=1))) == 1
    assert list(django_test_repository.find(offset=1, limit=1)) == [obj2]


def test_find_filter(django_test_repository, django_test_model):
    obj1 = get_obj(django_test_model)
    obj2 = get_obj(django_test_model)
    django_test_repository.add(obj1)
    django_test_repository.add(obj2)

    from fractal_specifications.generic.specification import Specification

    assert len(list(django_test_repository.find(Specification.parse(id=obj1.id)))) == 1
    assert list(django_test_repository.find(Specification.parse(id=obj1.id))) == [obj1]


def test_find_one(django_test_repository, django_test_model):
    obj1 = get_obj(django_test_model)
    obj2 = get_obj(django_test_model)
    django_test_repository.add(obj1)
    django_test_repository.add(obj2)

    from fractal_specifications.generic.specification import Specification

    assert django_test_repository.find_one(Specification.parse(id=obj1.id)) == obj1


def test_find_one_error(django_test_repository, django_test_model):
    from fractal_specifications.generic.specification import Specification

    from fractal_repositories.exceptions import ObjectNotFoundException

    with pytest.raises(ObjectNotFoundException):
        django_test_repository.find_one(Specification.parse(id="1"))


def test_add(django_test_repository, django_test_model):
    obj = get_obj(django_test_model)
    django_test_repository.add(obj)

    assert len(list(django_test_repository.find())) == 1
    assert list(django_test_repository.find())[0] == obj


def test_update(django_test_repository, django_test_model):
    obj = get_obj(django_test_model)
    django_test_repository.add(obj)

    obj.name = "test"
    django_test_repository.update(obj)

    assert len(list(django_test_repository.find())) == 1
    assert list(django_test_repository.find())[0] == obj


def test_update_error(django_test_repository, django_test_model):
    obj = get_obj(django_test_model)

    from fractal_repositories.exceptions import ObjectNotFoundException

    with pytest.raises(ObjectNotFoundException):
        django_test_repository.update(obj)


def test_update_upsert(django_test_repository, django_test_model):
    obj = get_obj(django_test_model)
    django_test_repository.update(obj, upsert=True)

    assert len(list(django_test_repository.find())) == 1
    assert list(django_test_repository.find())[0] == obj


def test_remove_one(django_test_repository, django_test_model):
    obj = get_obj(django_test_model)
    django_test_repository.add(obj)

    from fractal_specifications.generic.specification import Specification

    django_test_repository.remove_one(Specification.parse(id=obj.id))

    assert len(list(django_test_repository.find())) == 0
