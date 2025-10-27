from abc import ABC
from dataclasses import dataclass
from unittest.mock import MagicMock, patch

import pytest


@pytest.fixture
def postgres_test_model():
    from fractal_repositories.core.entity import Entity

    @dataclass
    class TestModelPostgres(Entity):
        id: str
        name: str = "test"
        description: str = "test"

    return TestModelPostgres


@pytest.fixture
def postgres_test_repository(postgres_test_model):
    from fractal_repositories.contrib.postgresql.mixins import (
        PostgresRepositoryMixin,
    )
    from fractal_repositories.core.repositories import Repository

    class TestRepository(Repository[postgres_test_model], ABC):
        entity = postgres_test_model

    class PostgresTestRepository(
        TestRepository, PostgresRepositoryMixin[postgres_test_model]
    ): ...

    # Mock the database connection
    with patch("psycopg2.connect") as mock_connect:
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_connect.return_value.__enter__ = MagicMock(return_value=mock_conn)
        mock_connect.return_value.__exit__ = MagicMock(return_value=False)
        mock_conn.cursor.return_value.__enter__ = MagicMock(return_value=mock_cursor)
        mock_conn.cursor.return_value.__exit__ = MagicMock(return_value=False)

        repo = PostgresTestRepository(
            postgres_host="localhost",
            postgres_port="5432",
            postgres_db="testdb",
            postgres_user="testuser",
            postgres_password="testpass",
            table="test",
        )
        repo._mock_connect = mock_connect
        repo._mock_conn = mock_conn
        repo._mock_cursor = mock_cursor
        yield repo
