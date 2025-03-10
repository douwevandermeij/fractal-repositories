import pytest


def test_is_healthy(sqlalchemy_test_repository):
    assert sqlalchemy_test_repository.is_healthy()


def test_is_healthy_error(sqlalchemy_test_repository):
    sqlalchemy_test_repository.session_factory = None
    assert not sqlalchemy_test_repository.is_healthy()


def test_add(sqlalchemy_test_repository, sqlalchemy_test_model):
    from fractal_specifications.generic.operators import EqualsSpecification

    obj = sqlalchemy_test_model("test")
    res = sqlalchemy_test_repository.add(obj)

    assert res == obj

    res = sqlalchemy_test_repository.find_one(EqualsSpecification("id", "test"))

    assert res == obj
    assert res.name == "test"


def test_add_error(sqlalchemy_test_repository, sqlalchemy_test_model):
    obj = sqlalchemy_test_model("test")
    obj.name = obj

    from fractal_repositories.contrib.sqlalchemy.mixins import SqlAlchemyException

    with pytest.raises(SqlAlchemyException):
        sqlalchemy_test_repository.add(obj)


def test_find_no_spec(sqlalchemy_test_repository, sqlalchemy_test_model):
    obj1 = sqlalchemy_test_model("test1")
    obj2 = sqlalchemy_test_model("test2")
    sqlalchemy_test_repository.add(obj1)
    sqlalchemy_test_repository.add(obj2)

    res = list(sqlalchemy_test_repository.find())

    assert len(res) == 2
    assert res == [obj1, obj2]


def test_count(sqlalchemy_test_repository, sqlalchemy_test_model):
    obj1 = sqlalchemy_test_model("test1")
    obj2 = sqlalchemy_test_model("test2")
    sqlalchemy_test_repository.add(obj1)
    sqlalchemy_test_repository.add(obj2)

    assert sqlalchemy_test_repository.count() == 2


def test_find_order_by_offset_limit(sqlalchemy_test_repository, sqlalchemy_test_model):
    obj1 = sqlalchemy_test_model("1", "test1")
    obj2 = sqlalchemy_test_model("2", "test2")
    sqlalchemy_test_repository.add(obj1)
    sqlalchemy_test_repository.add(obj2)

    assert list(sqlalchemy_test_repository.find(limit=1)) == [obj1]
    assert list(sqlalchemy_test_repository.find(limit=1, order_by="name")) == [obj1]
    assert list(sqlalchemy_test_repository.find(limit=1, order_by="-name")) == [obj2]
    assert list(
        sqlalchemy_test_repository.find(offset=1, limit=1, order_by="name")
    ) == [obj2]
    assert list(
        sqlalchemy_test_repository.find(offset=1, limit=1, order_by="-name")
    ) == [obj1]
    assert list(sqlalchemy_test_repository.find(offset=2, limit=1)) == []


def test_find_order_by_offset_limit_with_spec(
    sqlalchemy_test_repository, sqlalchemy_test_model
):
    from fractal_specifications.generic.operators import EqualsSpecification

    obj1 = sqlalchemy_test_model("1", "test1")
    obj2 = sqlalchemy_test_model("2", "test2")
    sqlalchemy_test_repository.add(obj1)
    sqlalchemy_test_repository.add(obj2)

    spec = EqualsSpecification("id", "1")

    assert list(sqlalchemy_test_repository.find(spec, limit=1)) == [obj1]
    assert list(sqlalchemy_test_repository.find(spec, limit=1, order_by="name")) == [
        obj1
    ]
    assert list(sqlalchemy_test_repository.find(spec, limit=1, order_by="-name")) == [
        obj1
    ]
    assert (
        list(sqlalchemy_test_repository.find(spec, offset=1, limit=1, order_by="name"))
        == []
    )
    assert (
        list(sqlalchemy_test_repository.find(spec, offset=1, limit=1, order_by="-name"))
        == []
    )
    assert list(sqlalchemy_test_repository.find(spec, offset=2, limit=1)) == []


def test_find_order_by_offset_limit_with_or_spec(
    sqlalchemy_test_repository, sqlalchemy_test_model
):
    from fractal_specifications.generic.operators import EqualsSpecification

    obj1 = sqlalchemy_test_model("1", "test1")
    obj2 = sqlalchemy_test_model("2", "test2")
    sqlalchemy_test_repository.add(obj1)
    sqlalchemy_test_repository.add(obj2)

    spec = EqualsSpecification("id", "1") | EqualsSpecification("name", "test2")

    assert list(sqlalchemy_test_repository.find(spec, limit=1)) == [obj1]
    assert list(sqlalchemy_test_repository.find(spec, limit=1, order_by="name")) == [
        obj1
    ]
    assert list(sqlalchemy_test_repository.find(spec, limit=1, order_by="-name")) == [
        obj2
    ]
    assert list(
        sqlalchemy_test_repository.find(spec, offset=1, limit=1, order_by="name")
    ) == [obj2]
    assert list(
        sqlalchemy_test_repository.find(spec, offset=1, limit=1, order_by="-name")
    ) == [obj1]
    assert list(sqlalchemy_test_repository.find(spec, offset=2, limit=1)) == []


def test_find_with_spec(sqlalchemy_test_repository, sqlalchemy_test_model):
    from fractal_specifications.generic.operators import EqualsSpecification

    obj1 = sqlalchemy_test_model("test1")
    obj2 = sqlalchemy_test_model("test2")
    sqlalchemy_test_repository.add(obj1)
    sqlalchemy_test_repository.add(obj2)

    res = list(sqlalchemy_test_repository.find(EqualsSpecification("id", "test1")))

    assert len(res) == 1
    assert res[0] == obj1


def test_find_with_spec_no_result(sqlalchemy_test_repository, sqlalchemy_test_model):
    from fractal_specifications.generic.operators import EqualsSpecification

    obj1 = sqlalchemy_test_model("test1")
    obj2 = sqlalchemy_test_model("test2")
    sqlalchemy_test_repository.add(obj1)
    sqlalchemy_test_repository.add(obj2)

    res = list(sqlalchemy_test_repository.find(EqualsSpecification("id", "no_result")))

    assert len(res) == 0


def test_find_with_spec_multiple_results(
    sqlalchemy_test_repository, sqlalchemy_test_model
):
    from fractal_specifications.generic.operators import EqualsSpecification

    obj1 = sqlalchemy_test_model("test1")
    obj2 = sqlalchemy_test_model("test2")
    sqlalchemy_test_repository.add(obj1)
    sqlalchemy_test_repository.add(obj2)

    res = list(sqlalchemy_test_repository.find(EqualsSpecification("name", "test")))

    assert len(res) == 2
    assert res == [obj1, obj2]


def test_find_with_and_spec(sqlalchemy_test_repository, sqlalchemy_test_model):
    from fractal_specifications.generic.operators import EqualsSpecification

    obj1 = sqlalchemy_test_model("test1")
    obj2 = sqlalchemy_test_model("test2")
    sqlalchemy_test_repository.add(obj1)
    sqlalchemy_test_repository.add(obj2)

    from fractal_specifications.generic.collections import AndSpecification

    res = list(
        sqlalchemy_test_repository.find(
            AndSpecification(
                [
                    EqualsSpecification("name", "test"),
                    EqualsSpecification("description", "test"),
                ]
            )
        )
    )

    assert len(res) == 2
    assert res == [obj1, obj2]


def test_find_with_or_spec(sqlalchemy_test_repository, sqlalchemy_test_model):
    from fractal_specifications.generic.collections import OrSpecification
    from fractal_specifications.generic.operators import EqualsSpecification

    obj1 = sqlalchemy_test_model("test1")
    obj2 = sqlalchemy_test_model("test2")
    sqlalchemy_test_repository.add(obj1)
    sqlalchemy_test_repository.add(obj2)

    res = list(
        sqlalchemy_test_repository.find(
            OrSpecification(
                [EqualsSpecification("id", "test1"), EqualsSpecification("id", "test2")]
            )
        )
    )

    assert len(res) == 2
    assert res == [obj1, obj2]


def test_update(sqlalchemy_test_repository, sqlalchemy_test_model):
    from fractal_specifications.generic.operators import EqualsSpecification

    obj = sqlalchemy_test_model("test")
    sqlalchemy_test_repository.add(obj)

    obj.name = "update"
    res = sqlalchemy_test_repository.update(obj)

    assert res == obj
    assert res.name == "update"

    res = sqlalchemy_test_repository.find_one(EqualsSpecification("id", "test"))

    assert res == obj
    assert res.name == "update"


def test_update_error(sqlalchemy_test_repository, sqlalchemy_test_model):
    obj = sqlalchemy_test_model("test")
    sqlalchemy_test_repository.add(obj)

    obj.name = obj

    from fractal_repositories.contrib.sqlalchemy.mixins import SqlAlchemyException

    with pytest.raises(SqlAlchemyException):
        sqlalchemy_test_repository.update(obj)


def test_update_add_item(
    sqlalchemy_test_repository, sqlalchemy_test_model, sqlalchemy_test_sub_model
):
    from fractal_specifications.generic.operators import EqualsSpecification

    obj = sqlalchemy_test_model("test")
    sqlalchemy_test_repository.add(obj)

    sub_obj = sqlalchemy_test_sub_model("item", item_id=obj.id)
    obj.items = [sub_obj]
    res = sqlalchemy_test_repository.update(obj)

    assert res == obj
    assert res.items == [sub_obj]

    res = sqlalchemy_test_repository.find_one(EqualsSpecification("id", "test"))

    assert res == obj
    assert res.items == [sub_obj]


def test_update_delete_item(
    sqlalchemy_test_repository, sqlalchemy_test_model, sqlalchemy_test_sub_model
):
    from fractal_specifications.generic.operators import EqualsSpecification

    obj = sqlalchemy_test_model("test")
    sqlalchemy_test_repository.add(obj)
    sub_obj = sqlalchemy_test_sub_model("item", item_id=obj.id)
    obj.items = [sub_obj]
    sqlalchemy_test_repository.update(obj)

    obj.items = []
    res = sqlalchemy_test_repository.update(obj)

    assert res == obj
    assert res.items == []

    res = sqlalchemy_test_repository.find_one(EqualsSpecification("id", "test"))

    assert res == obj
    assert res.items == []


def test_update_item(
    sqlalchemy_test_repository, sqlalchemy_test_model, sqlalchemy_test_sub_model
):
    from fractal_specifications.generic.operators import EqualsSpecification

    obj = sqlalchemy_test_model("test")
    sqlalchemy_test_repository.add(obj)
    sub_obj = sqlalchemy_test_sub_model("item", item_id=obj.id)
    obj.items = [sub_obj]
    sqlalchemy_test_repository.update(obj)

    obj.items[0].name = "update"
    sqlalchemy_test_repository.update(obj)

    res = sqlalchemy_test_repository.find_one(EqualsSpecification("id", "test"))

    assert res == obj
    assert res.items[0].name == "update"


def test_update_item_error(
    sqlalchemy_test_repository_error, sqlalchemy_test_model, sqlalchemy_test_sub_model
):
    obj = sqlalchemy_test_model("test")
    sqlalchemy_test_repository_error.add(obj)
    sub_obj = sqlalchemy_test_sub_model("item", item_id=obj.id)
    obj.items = [sub_obj]

    from fractal_repositories.contrib.sqlalchemy.mixins import (
        UnknownListItemTypeException,
    )

    with pytest.raises(UnknownListItemTypeException):
        sqlalchemy_test_repository_error.update(obj)


def test_update_upsert(sqlalchemy_test_repository, sqlalchemy_test_model):
    from fractal_specifications.generic.operators import EqualsSpecification

    obj = sqlalchemy_test_model("test")

    res = sqlalchemy_test_repository.update(obj, upsert=True)

    assert res == obj

    res = sqlalchemy_test_repository.find_one(EqualsSpecification("id", "test"))

    assert res == obj
    assert res.name == "test"


def test_update_upsert_error(sqlalchemy_test_repository, sqlalchemy_test_model):
    obj = sqlalchemy_test_model("test")

    from fractal_repositories.exceptions import ObjectNotFoundException

    with pytest.raises(ObjectNotFoundException):
        sqlalchemy_test_repository.update(obj, upsert=False)


def test_remove_one(sqlalchemy_test_repository, sqlalchemy_test_model):
    from fractal_specifications.generic.operators import EqualsSpecification

    obj1 = sqlalchemy_test_model("test1")
    obj2 = sqlalchemy_test_model("test2")
    sqlalchemy_test_repository.add(obj1)
    sqlalchemy_test_repository.add(obj2)

    sqlalchemy_test_repository.remove_one(EqualsSpecification("id", "test1"))

    res = list(sqlalchemy_test_repository.find())

    assert len(res) == 1
    assert res == [obj2]


def test_find_one(sqlalchemy_test_repository, sqlalchemy_test_model):
    from fractal_specifications.generic.operators import EqualsSpecification

    obj1 = sqlalchemy_test_model("test1")
    obj2 = sqlalchemy_test_model("test2")
    sqlalchemy_test_repository.add(obj1)
    sqlalchemy_test_repository.add(obj2)

    res = sqlalchemy_test_repository.find_one(EqualsSpecification("id", "test2"))

    assert res == obj2


def test_find_one_error(sqlalchemy_test_repository, sqlalchemy_test_model):
    from fractal_specifications.generic.operators import EqualsSpecification

    from fractal_repositories.exceptions import ObjectNotFoundException

    with pytest.raises(ObjectNotFoundException):
        sqlalchemy_test_repository.find_one(EqualsSpecification("id", "test"))
