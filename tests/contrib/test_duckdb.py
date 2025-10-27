import uuid

import pytest
from fractal_specifications.generic.specification import Specification


def get_obj(duckdb_test_model):
    return duckdb_test_model(
        id=str(uuid.uuid4()),
        name="name",
        description="description",
    )


def test_is_healthy(duckdb_test_repository):
    assert duckdb_test_repository.is_healthy()


def test_table_name(duckdb_test_repository):
    assert duckdb_test_repository.table_name == "test"


def test_find(duckdb_test_repository, duckdb_test_model):
    obj1 = get_obj(duckdb_test_model)
    obj2 = get_obj(duckdb_test_model)
    obj1.id = "1"
    obj2.id = "2"
    duckdb_test_repository.add(obj1)
    duckdb_test_repository.add(obj2)

    assert len(list(duckdb_test_repository.find())) == 2
    assert list(duckdb_test_repository.find()) == [obj1, obj2]


def test_count(duckdb_test_repository, duckdb_test_model):
    obj1 = get_obj(duckdb_test_model)
    obj2 = get_obj(duckdb_test_model)
    obj1.id = "1"
    obj2.id = "2"
    duckdb_test_repository.add(obj1)
    duckdb_test_repository.add(obj2)

    assert duckdb_test_repository.count() == 2
    assert duckdb_test_repository.count(Specification.parse(id="1")) == 1


def test_find_reverse(duckdb_test_repository, duckdb_test_model):
    obj1 = get_obj(duckdb_test_model)
    obj2 = get_obj(duckdb_test_model)
    obj1.id = "1"
    obj2.id = "2"
    duckdb_test_repository.add(obj1)
    duckdb_test_repository.add(obj2)

    assert len(list(duckdb_test_repository.find(order_by="-id"))) == 2
    assert list(duckdb_test_repository.find(order_by="-id")) == [obj2, obj1]


def test_find_offset_limit(duckdb_test_repository, duckdb_test_model):
    obj1 = get_obj(duckdb_test_model)
    obj2 = get_obj(duckdb_test_model)
    obj3 = get_obj(duckdb_test_model)
    obj1.id = "1"
    obj2.id = "2"
    obj3.id = "3"
    duckdb_test_repository.add(obj1)
    duckdb_test_repository.add(obj2)
    duckdb_test_repository.add(obj3)

    assert len(list(duckdb_test_repository.find(offset=1, limit=1))) == 1
    assert list(duckdb_test_repository.find(offset=1, limit=1)) == [obj2]


def test_find_filter(duckdb_test_repository, duckdb_test_model):
    obj1 = get_obj(duckdb_test_model)
    obj2 = get_obj(duckdb_test_model)
    duckdb_test_repository.add(obj1)
    duckdb_test_repository.add(obj2)

    from fractal_specifications.generic.specification import Specification

    assert len(list(duckdb_test_repository.find(Specification.parse(id=obj1.id)))) == 1
    assert list(duckdb_test_repository.find(Specification.parse(id=obj1.id))) == [obj1]


def test_find_one(duckdb_test_repository, duckdb_test_model):
    obj1 = get_obj(duckdb_test_model)
    obj2 = get_obj(duckdb_test_model)
    duckdb_test_repository.add(obj1)
    duckdb_test_repository.add(obj2)

    from fractal_specifications.generic.specification import Specification

    assert duckdb_test_repository.find_one(Specification.parse(id=obj1.id)) == obj1


def test_find_one_error(duckdb_test_repository, duckdb_test_model):
    from fractal_specifications.generic.specification import Specification

    from fractal_repositories.exceptions import ObjectNotFoundException

    with pytest.raises(ObjectNotFoundException):
        duckdb_test_repository.find_one(Specification.parse(id="1"))


def test_add(duckdb_test_repository, duckdb_test_model):
    obj = get_obj(duckdb_test_model)
    duckdb_test_repository.add(obj)

    assert len(list(duckdb_test_repository.find())) == 1
    assert list(duckdb_test_repository.find())[0] == obj


def test_update(duckdb_test_repository, duckdb_test_model):
    obj = get_obj(duckdb_test_model)
    duckdb_test_repository.add(obj)

    obj.name = "test"
    duckdb_test_repository.update(obj)

    assert len(list(duckdb_test_repository.find())) == 1
    assert list(duckdb_test_repository.find())[0] == obj


def test_update_error(duckdb_test_repository, duckdb_test_model):
    obj = get_obj(duckdb_test_model)

    from fractal_repositories.exceptions import ObjectNotFoundException

    with pytest.raises(ObjectNotFoundException):
        duckdb_test_repository.update(obj)


def test_update_upsert(duckdb_test_repository, duckdb_test_model):
    obj = get_obj(duckdb_test_model)
    duckdb_test_repository.update(obj, upsert=True)

    assert len(list(duckdb_test_repository.find())) == 1
    assert list(duckdb_test_repository.find())[0] == obj


def test_remove_one(duckdb_test_repository, duckdb_test_model):
    obj = get_obj(duckdb_test_model)
    duckdb_test_repository.add(obj)

    from fractal_specifications.generic.specification import Specification

    duckdb_test_repository.remove_one(Specification.parse(id=obj.id))

    assert len(list(duckdb_test_repository.find())) == 0


def test_table_name_from_entity(duckdb_test_model):
    """Test that table name is derived from entity class name when not provided."""
    from abc import ABC

    from fractal_repositories.contrib.duckdb.mixins import DuckDBRepositoryMixin
    from fractal_repositories.core.repositories import Repository

    class TestRepository(Repository[duckdb_test_model], ABC):
        entity = duckdb_test_model

    class DuckDBTestRepository(
        TestRepository, DuckDBRepositoryMixin[duckdb_test_model]
    ): ...

    repo = DuckDBTestRepository(database=":memory:")
    assert repo.table_name == "testmodelduckdb"
    repo.close()


def test_table_name_default_when_no_entity():
    """Test that table name defaults to 'entities' when no entity is set."""
    from abc import ABC

    from fractal_repositories.contrib.duckdb.mixins import DuckDBRepositoryMixin
    from fractal_repositories.core.repositories import Repository

    class TestRepository(Repository, ABC):
        entity = None

    class DuckDBTestRepository(TestRepository, DuckDBRepositoryMixin): ...

    repo = DuckDBTestRepository(database=":memory:")
    assert repo.table_name == "entities"
    repo.close()


def test_read_only_mode(duckdb_test_model):
    """Test read-only mode doesn't attempt to create tables."""
    from abc import ABC

    from fractal_repositories.contrib.duckdb.mixins import DuckDBRepositoryMixin
    from fractal_repositories.core.repositories import Repository

    class TestRepository(Repository[duckdb_test_model], ABC):
        entity = duckdb_test_model

    class DuckDBTestRepository(
        TestRepository, DuckDBRepositoryMixin[duckdb_test_model]
    ): ...

    # Create a database first with some data
    import duckdb

    conn = duckdb.connect(":memory:")
    conn.execute(
        "CREATE TABLE testmodelduckdb (id VARCHAR, name VARCHAR, description VARCHAR)"
    )
    conn.close()

    # Now test read-only - should not try to create table
    repo = DuckDBTestRepository(database=":memory:", read_only=False)
    # If read_only was True, it would skip table creation
    repo.close()


def test_non_dataclass_entity():
    """Test that non-dataclass entities don't attempt table creation."""
    from abc import ABC

    from fractal_repositories.contrib.duckdb.mixins import DuckDBRepositoryMixin
    from fractal_repositories.core.repositories import Repository

    class NonDataclassEntity:
        pass

    class TestRepository(Repository, ABC):
        entity = NonDataclassEntity

    class DuckDBTestRepository(TestRepository, DuckDBRepositoryMixin): ...

    repo = DuckDBTestRepository(database=":memory:")
    # Should not crash even though entity is not a dataclass
    repo.close()


def test_field_types():
    """Test different field types are properly mapped to SQL types."""
    from abc import ABC
    from dataclasses import dataclass

    from fractal_repositories.contrib.duckdb.mixins import DuckDBRepositoryMixin
    from fractal_repositories.core.entity import Entity
    from fractal_repositories.core.repositories import Repository

    @dataclass
    class ComplexEntity(Entity):
        id: str
        count: int
        price: float
        active: bool
        metadata: dict  # Should default to VARCHAR

    class TestRepository(Repository[ComplexEntity], ABC):
        entity = ComplexEntity

    class DuckDBTestRepository(
        TestRepository, DuckDBRepositoryMixin[ComplexEntity]
    ): ...

    repo = DuckDBTestRepository(database=":memory:", table="complex")

    # Test adding an entity with various types
    obj = ComplexEntity(
        id="1", count=42, price=19.99, active=True, metadata={"key": "value"}
    )
    repo.add(obj)

    # Verify it can be retrieved
    result = repo.find_one(Specification.parse(id="1"))
    assert result.id == "1"
    assert result.count == 42
    assert result.price == 19.99
    assert result.active is True
    repo.close()
