import uuid

import pytest
from fractal_specifications.generic.specification import Specification


def get_obj(firestore_test_model, now):
    return firestore_test_model(
        id=str(uuid.uuid4()),
        name="name",
        description="description",
        created_on=now.strftime("%Y-%m-%d"),
        created_at=now.isoformat(),
    )


def test_is_healthy(firestore_test_repository):
    assert firestore_test_repository.is_healthy()


def test_find(firestore_test_repository, firestore_test_model, now):
    obj1 = get_obj(firestore_test_model, now)
    obj2 = get_obj(firestore_test_model, now)
    obj1.id = "1"
    obj2.id = "2"
    firestore_test_repository.add(obj1)
    firestore_test_repository.add(obj2)

    assert len(list(firestore_test_repository.find())) == 2
    assert list(firestore_test_repository.find()) == [obj1, obj2]


def test_count(firestore_test_repository, firestore_test_model, now):
    obj1 = get_obj(firestore_test_model, now)
    obj2 = get_obj(firestore_test_model, now)
    obj1.id = "1"
    obj2.id = "2"
    firestore_test_repository.add(obj1)
    firestore_test_repository.add(obj2)

    assert firestore_test_repository.count() == 2
    assert firestore_test_repository.count(Specification.parse(id="1")) == 1


def test_find_reverse(firestore_test_repository, firestore_test_model, now):
    obj1 = get_obj(firestore_test_model, now)
    obj2 = get_obj(firestore_test_model, now)
    obj1.id = "1"
    obj2.id = "2"
    firestore_test_repository.add(obj1)
    firestore_test_repository.add(obj2)

    assert len(list(firestore_test_repository.find(order_by="-id"))) == 2
    assert list(firestore_test_repository.find(order_by="-id")) == [obj2, obj1]


def test_find_offset_limit(firestore_test_repository, firestore_test_model, now):
    obj1 = get_obj(firestore_test_model, now)
    obj2 = get_obj(firestore_test_model, now)
    obj3 = get_obj(firestore_test_model, now)
    obj1.id = "1"
    obj2.id = "2"
    obj3.id = "3"
    firestore_test_repository.add(obj1)
    firestore_test_repository.add(obj2)
    firestore_test_repository.add(obj3)

    assert len(list(firestore_test_repository.find(offset=1, limit=1))) == 1
    assert list(firestore_test_repository.find(offset=1, limit=1)) == [obj2]


def test_find_filter(firestore_test_repository, firestore_test_model, now):
    obj1 = get_obj(firestore_test_model, now)
    obj2 = get_obj(firestore_test_model, now)
    firestore_test_repository.add(obj1)
    firestore_test_repository.add(obj2)

    from fractal_specifications.generic.specification import Specification

    assert (
        len(list(firestore_test_repository.find(Specification.parse(id=obj1.id)))) == 1
    )
    assert list(firestore_test_repository.find(Specification.parse(id=obj1.id))) == [
        obj1
    ]


def test_find_one(firestore_test_repository, firestore_test_model, now):
    obj1 = get_obj(firestore_test_model, now)
    obj2 = get_obj(firestore_test_model, now)
    firestore_test_repository.add(obj1)
    firestore_test_repository.add(obj2)

    from fractal_specifications.generic.specification import Specification

    assert firestore_test_repository.find_one(Specification.parse(id=obj1.id)) == obj1


def test_find_one_error(firestore_test_repository, firestore_test_model):
    from fractal_specifications.generic.specification import Specification

    from fractal_repositories.exceptions import ObjectNotFoundException

    with pytest.raises(ObjectNotFoundException):
        firestore_test_repository.find_one(Specification.parse(id="1"))


def test_add(firestore_test_repository, firestore_test_model, now):
    obj = get_obj(firestore_test_model, now)
    firestore_test_repository.add(obj)

    assert len(list(firestore_test_repository.find())) == 1
    assert list(firestore_test_repository.find())[0] == obj


def test_update(firestore_test_repository, firestore_test_model, now):
    obj = get_obj(firestore_test_model, now)
    firestore_test_repository.add(obj)

    obj.name = "test"
    firestore_test_repository.update(obj)

    assert len(list(firestore_test_repository.find())) == 1
    assert list(firestore_test_repository.find())[0] == obj


def test_update_error(firestore_test_repository, firestore_test_model, now):
    obj = get_obj(firestore_test_model, now)

    from fractal_repositories.exceptions import ObjectNotFoundException

    with pytest.raises(ObjectNotFoundException):
        firestore_test_repository.update(obj)


def test_update_upsert(firestore_test_repository, firestore_test_model, now):
    obj = get_obj(firestore_test_model, now)
    firestore_test_repository.update(obj, upsert=True)

    assert len(list(firestore_test_repository.find())) == 1
    assert list(firestore_test_repository.find())[0] == obj


def test_remove_one(firestore_test_repository, firestore_test_model, now):
    obj = get_obj(firestore_test_model, now)
    firestore_test_repository.add(obj)

    from fractal_specifications.generic.specification import Specification

    firestore_test_repository.remove_one(Specification.parse(id=obj.id))

    assert len(list(firestore_test_repository.find())) == 0


def test_datetime_filters_match_stored_strings(
    firestore_test_repository, firestore_test_model
):
    from datetime import datetime, timedelta, timezone

    start = datetime(2026, 9, 22, tzinfo=timezone.utc)
    for hours in (-3, 2, 10, 26):
        firestore_test_repository.add(
            firestore_test_model(
                id=str(hours), created_at=start + timedelta(hours=hours)
            )
        )
    # One condition per query: mock-firestore's Query.where() takes no
    # filter= keyword, so only the first where() of a chain can run here.
    after = Specification.parse(created_at__gte=start + timedelta(hours=1))
    before = Specification.parse(created_at__lt=start)

    assert sorted(t.id for t in firestore_test_repository.find(after)) == [
        "10",
        "2",
        "26",
    ]
    assert firestore_test_repository.count(after) == 3
    assert firestore_test_repository.find_one(before).id == "-3"
