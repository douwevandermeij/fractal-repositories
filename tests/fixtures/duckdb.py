from abc import ABC
from dataclasses import dataclass

import pytest


@pytest.fixture
def duckdb_test_model():
    from fractal_repositories.core.entity import Entity

    @dataclass
    class TestModelDuckDB(Entity):
        id: str
        name: str = "test"
        description: str = "test"

    return TestModelDuckDB


@pytest.fixture
def duckdb_test_repository(duckdb_test_model):
    from fractal_repositories.contrib.duckdb.mixins import DuckDBRepositoryMixin
    from fractal_repositories.core.repositories import Repository

    class TestRepository(Repository[duckdb_test_model], ABC):
        entity = duckdb_test_model

    class DuckDBTestRepository(
        TestRepository, DuckDBRepositoryMixin[duckdb_test_model]
    ): ...

    return DuckDBTestRepository(
        database=":memory:",
        table="test",
    )
