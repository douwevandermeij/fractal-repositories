import pytest


def test_is_healthy(file_repository):
    assert file_repository.is_healthy()


def test_add(file_repository, an_object):
    file_repository.add(an_object)

    assert len(file_repository.entities) == 1
    assert list(file_repository.entities.values())[0] == an_object


def test_update(file_repository, an_object, mocker_file_open_data):
    file_repository.add(an_object)

    assert list(file_repository.entities.values())[0].name != "update"
    mocker_file_open_data(file_repository.entities.values())

    an_object.name = "update"
    file_repository.update(an_object)

    assert len(file_repository.entities) == 1
    assert list(file_repository.entities.values())[0].name == "update"


def test_update_upsert(file_repository, an_object):
    file_repository.update(an_object, upsert=True)

    assert len(file_repository.entities) == 1
    assert list(file_repository.entities.values())[0] == an_object


def test_update_upsert_ignore(file_repository, an_object):
    from fractal_repositories.exceptions import ObjectNotFoundException

    with pytest.raises(ObjectNotFoundException):
        file_repository.update(an_object)

    assert len(file_repository.entities) == 0


def test_remove_one(file_repository, an_object, mocker_file_open_data):
    file_repository.add(an_object)
    mocker_file_open_data(file_repository.entities.values())

    from fractal_specifications.generic.specification import Specification

    file_repository.remove_one(Specification.parse(id=an_object.id))

    assert len(file_repository.entities) == 0


def test_find_one(file_repository, an_object, mocker_file_open_data):
    file_repository.add(an_object)
    mocker_file_open_data(file_repository.entities.values())

    from fractal_specifications.generic.specification import Specification

    assert file_repository.find_one(Specification.parse(id=an_object.id)) == an_object


def test_find(file_repository, an_object, mocker_file_open_data):
    file_repository.add(an_object)
    mocker_file_open_data(file_repository.entities.values())

    assert len(list(file_repository.find())) == 1


def test_find_reverse(
    file_repository, an_object, another_object, mocker_file_open_data
):
    file_repository.add(an_object)
    file_repository.add(another_object)
    mocker_file_open_data(file_repository.entities.values())

    assert [i.id for i in file_repository.find(order_by="id")] == [
        an_object.id,
        another_object.id,
    ]
    assert [i.id for i in file_repository.find(order_by="-id")] == [
        another_object.id,
        an_object.id,
    ]


def test_find_limit(file_repository, an_object, another_object, mocker_file_open_data):
    file_repository.add(an_object)
    file_repository.add(another_object)
    mocker_file_open_data(file_repository.entities.values())

    assert len(list(file_repository.find())) == 2
    assert len(list(file_repository.find(limit=1))) == 1


def test_find_with_specification(file_repository, an_object, mocker_file_open_data):
    file_repository.add(an_object)
    mocker_file_open_data(file_repository.entities.values())

    from fractal_specifications.generic.specification import Specification

    assert len(list(file_repository.find(Specification.parse(id=an_object.id)))) == 1


def test_find_with_specification_empty(file_repository, an_object):
    file_repository.add(an_object)

    from fractal_specifications.generic.specification import Specification

    assert len(list(file_repository.find(Specification.parse(id=2)))) == 0


def test_find_path_doesnt_exist(file_repository, mocker_os_path_exists_error):
    # with pytest.raises(RepositoryException):
    #     next(file_repository.find())
    assert list(file_repository.find()) == []
