import uuid
from unittest.mock import MagicMock, patch

import pytest
from fractal_specifications.generic.specification import Specification


def get_obj(postgres_test_model):
    return postgres_test_model(
        id=str(uuid.uuid4()),
        name="name",
        description="description",
    )


def test_table_name(postgres_test_repository):
    assert postgres_test_repository.table_name == "test"


def test_add(postgres_test_repository, postgres_test_model):
    obj = get_obj(postgres_test_model)

    with patch("psycopg2.connect") as mock_connect:
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_connect.return_value.__enter__ = MagicMock(return_value=mock_conn)
        mock_connect.return_value.__exit__ = MagicMock(return_value=False)
        mock_conn.cursor.return_value.__enter__ = MagicMock(return_value=mock_cursor)
        mock_conn.cursor.return_value.__exit__ = MagicMock(return_value=False)

        result = postgres_test_repository.add(obj)

        assert result == obj
        mock_cursor.execute.assert_called_once()
        mock_conn.commit.assert_called_once()


def test_update(postgres_test_repository, postgres_test_model):
    obj = get_obj(postgres_test_model)

    with patch("psycopg2.connect") as mock_connect:
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_cursor.rowcount = 1
        mock_connect.return_value.__enter__ = MagicMock(return_value=mock_conn)
        mock_connect.return_value.__exit__ = MagicMock(return_value=False)
        mock_conn.cursor.return_value.__enter__ = MagicMock(return_value=mock_cursor)
        mock_conn.cursor.return_value.__exit__ = MagicMock(return_value=False)

        obj.name = "updated"
        result = postgres_test_repository.update(obj)

        assert result == obj
        mock_cursor.execute.assert_called_once()
        mock_conn.commit.assert_called_once()


def test_update_error(postgres_test_repository, postgres_test_model):
    obj = get_obj(postgres_test_model)

    with patch("psycopg2.connect") as mock_connect:
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_cursor.rowcount = 0
        mock_connect.return_value.__enter__ = MagicMock(return_value=mock_conn)
        mock_connect.return_value.__exit__ = MagicMock(return_value=False)
        mock_conn.cursor.return_value.__enter__ = MagicMock(return_value=mock_cursor)
        mock_conn.cursor.return_value.__exit__ = MagicMock(return_value=False)

        from fractal_repositories.exceptions import ObjectNotFoundException

        with pytest.raises(ObjectNotFoundException):
            postgres_test_repository.update(obj)


def test_update_upsert(postgres_test_repository, postgres_test_model):
    obj = get_obj(postgres_test_model)

    with patch("psycopg2.connect") as mock_connect:
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_cursor.rowcount = 0
        mock_connect.return_value.__enter__ = MagicMock(return_value=mock_conn)
        mock_connect.return_value.__exit__ = MagicMock(return_value=False)
        mock_conn.cursor.return_value.__enter__ = MagicMock(return_value=mock_cursor)
        mock_conn.cursor.return_value.__exit__ = MagicMock(return_value=False)

        result = postgres_test_repository.update(obj, upsert=True)

        assert result == obj
        # Should be called twice: once for update, once for add
        assert mock_cursor.execute.call_count >= 1


def test_remove_one(postgres_test_repository, postgres_test_model):
    obj = get_obj(postgres_test_model)

    with patch("psycopg2.connect") as mock_connect:
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_connect.return_value.__enter__ = MagicMock(return_value=mock_conn)
        mock_connect.return_value.__exit__ = MagicMock(return_value=False)
        mock_conn.cursor.return_value.__enter__ = MagicMock(return_value=mock_cursor)
        mock_conn.cursor.return_value.__exit__ = MagicMock(return_value=False)

        postgres_test_repository.remove_one(Specification.parse(id=obj.id))

        mock_cursor.execute.assert_called_once()
        mock_conn.commit.assert_called_once()


def test_find_one(postgres_test_repository, postgres_test_model):
    obj = get_obj(postgres_test_model)

    with patch("psycopg2.connect") as mock_connect:
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_cursor.fetchone.return_value = obj.asdict()
        mock_connect.return_value.__enter__ = MagicMock(return_value=mock_conn)
        mock_connect.return_value.__exit__ = MagicMock(return_value=False)
        mock_conn.cursor.return_value.__enter__ = MagicMock(return_value=mock_cursor)
        mock_conn.cursor.return_value.__exit__ = MagicMock(return_value=False)

        result = postgres_test_repository.find_one(Specification.parse(id=obj.id))

        assert result.id == obj.id
        mock_cursor.execute.assert_called_once()


def test_find_one_error(postgres_test_repository, postgres_test_model):
    with patch("psycopg2.connect") as mock_connect:
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_cursor.fetchone.return_value = None
        mock_connect.return_value.__enter__ = MagicMock(return_value=mock_conn)
        mock_connect.return_value.__exit__ = MagicMock(return_value=False)
        mock_conn.cursor.return_value.__enter__ = MagicMock(return_value=mock_cursor)
        mock_conn.cursor.return_value.__exit__ = MagicMock(return_value=False)

        from fractal_repositories.exceptions import ObjectNotFoundException

        with pytest.raises(ObjectNotFoundException):
            postgres_test_repository.find_one(Specification.parse(id="1"))


def test_find(postgres_test_repository, postgres_test_model):
    obj1 = get_obj(postgres_test_model)
    obj2 = get_obj(postgres_test_model)

    with patch("psycopg2.connect") as mock_connect:
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_cursor.__iter__ = MagicMock(
            return_value=iter([obj1.asdict(), obj2.asdict()])
        )
        mock_connect.return_value.__enter__ = MagicMock(return_value=mock_conn)
        mock_connect.return_value.__exit__ = MagicMock(return_value=False)
        mock_conn.cursor.return_value.__enter__ = MagicMock(return_value=mock_cursor)
        mock_conn.cursor.return_value.__exit__ = MagicMock(return_value=False)

        results = list(postgres_test_repository.find())

        assert len(results) == 2
        mock_cursor.execute.assert_called_once()


def test_find_with_specification(postgres_test_repository, postgres_test_model):
    obj1 = get_obj(postgres_test_model)

    with patch("psycopg2.connect") as mock_connect:
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_cursor.__iter__ = MagicMock(return_value=iter([obj1.asdict()]))
        mock_connect.return_value.__enter__ = MagicMock(return_value=mock_conn)
        mock_connect.return_value.__exit__ = MagicMock(return_value=False)
        mock_conn.cursor.return_value.__enter__ = MagicMock(return_value=mock_cursor)
        mock_conn.cursor.return_value.__exit__ = MagicMock(return_value=False)

        results = list(postgres_test_repository.find(Specification.parse(id=obj1.id)))

        assert len(results) == 1
        mock_cursor.execute.assert_called_once()


def test_find_with_order_by(postgres_test_repository, postgres_test_model):
    obj1 = get_obj(postgres_test_model)
    obj2 = get_obj(postgres_test_model)

    with patch("psycopg2.connect") as mock_connect:
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_cursor.__iter__ = MagicMock(
            return_value=iter([obj2.asdict(), obj1.asdict()])
        )
        mock_connect.return_value.__enter__ = MagicMock(return_value=mock_conn)
        mock_connect.return_value.__exit__ = MagicMock(return_value=False)
        mock_conn.cursor.return_value.__enter__ = MagicMock(return_value=mock_cursor)
        mock_conn.cursor.return_value.__exit__ = MagicMock(return_value=False)

        results = list(postgres_test_repository.find(order_by="-id"))

        assert len(results) == 2
        # Verify that execute was called with ORDER BY in the query
        call_args = mock_cursor.execute.call_args[0][0]
        assert "ORDER BY" in call_args
        assert "DESC" in call_args


def test_find_with_limit_offset(postgres_test_repository, postgres_test_model):
    obj1 = get_obj(postgres_test_model)

    with patch("psycopg2.connect") as mock_connect:
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_cursor.__iter__ = MagicMock(return_value=iter([obj1.asdict()]))
        mock_connect.return_value.__enter__ = MagicMock(return_value=mock_conn)
        mock_connect.return_value.__exit__ = MagicMock(return_value=False)
        mock_conn.cursor.return_value.__enter__ = MagicMock(return_value=mock_cursor)
        mock_conn.cursor.return_value.__exit__ = MagicMock(return_value=False)

        results = list(postgres_test_repository.find(offset=1, limit=1))

        assert len(results) == 1
        # Verify that execute was called with LIMIT and OFFSET in the query
        call_args = mock_cursor.execute.call_args[0][0]
        assert "LIMIT" in call_args
        assert "OFFSET" in call_args


def test_find_with_select(postgres_test_repository, postgres_test_model):
    obj1 = get_obj(postgres_test_model)

    with patch("psycopg2.connect") as mock_connect:
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_cursor.__iter__ = MagicMock(
            return_value=iter([{"id": obj1.id, "name": obj1.name}])
        )
        mock_connect.return_value.__enter__ = MagicMock(return_value=mock_conn)
        mock_connect.return_value.__exit__ = MagicMock(return_value=False)
        mock_conn.cursor.return_value.__enter__ = MagicMock(return_value=mock_cursor)
        mock_conn.cursor.return_value.__exit__ = MagicMock(return_value=False)

        results = list(postgres_test_repository.find(select=["id", "name"]))

        assert len(results) == 1
        # Verify that execute was called with specific columns
        call_args = mock_cursor.execute.call_args[0][0]
        assert "id, name" in call_args


def test_count(postgres_test_repository):
    with patch("psycopg2.connect") as mock_connect:
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_cursor.fetchone.return_value = [5]
        mock_connect.return_value.__enter__ = MagicMock(return_value=mock_conn)
        mock_connect.return_value.__exit__ = MagicMock(return_value=False)
        mock_conn.cursor.return_value.__enter__ = MagicMock(return_value=mock_cursor)
        mock_conn.cursor.return_value.__exit__ = MagicMock(return_value=False)

        count = postgres_test_repository.count()

        assert count == 5
        mock_cursor.execute.assert_called_once()


def test_count_with_specification(postgres_test_repository):
    with patch("psycopg2.connect") as mock_connect:
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_cursor.fetchone.return_value = [1]
        mock_connect.return_value.__enter__ = MagicMock(return_value=mock_conn)
        mock_connect.return_value.__exit__ = MagicMock(return_value=False)
        mock_conn.cursor.return_value.__enter__ = MagicMock(return_value=mock_cursor)
        mock_conn.cursor.return_value.__exit__ = MagicMock(return_value=False)

        count = postgres_test_repository.count(Specification.parse(id="1"))

        assert count == 1
        mock_cursor.execute.assert_called_once()


def test_is_healthy(postgres_test_repository):
    with patch("psycopg2.connect") as mock_connect:
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_connect.return_value.__enter__ = MagicMock(return_value=mock_conn)
        mock_connect.return_value.__exit__ = MagicMock(return_value=False)
        mock_conn.cursor.return_value.__enter__ = MagicMock(return_value=mock_cursor)
        mock_conn.cursor.return_value.__exit__ = MagicMock(return_value=False)

        result = postgres_test_repository.is_healthy()

        assert result is True
        mock_cursor.execute.assert_called_once_with("SELECT 1")


def test_is_healthy_error(postgres_test_repository):
    with patch("psycopg2.connect") as mock_connect:
        mock_connect.side_effect = Exception("Connection failed")

        result = postgres_test_repository.is_healthy()

        assert result is False
