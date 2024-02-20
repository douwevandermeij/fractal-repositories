from abc import ABC
from dataclasses import dataclass

import pytest


@pytest.fixture
def mongo_test_model():
    from fractal_repositories.core.entity import Entity

    @dataclass
    class TestModelMongo(Entity):
        id: str
        name: str = "test"
        description: str = "test"

    return TestModelMongo


@pytest.fixture
def mongo_test_repository(mongo_test_model):
    from fractal_repositories.contrib.mongo.mixins import MongoRepositoryMixin
    from fractal_repositories.core.repositories import Repository

    class TestRepository(Repository[mongo_test_model], ABC):
        entity = mongo_test_model

    class MongoTestRepository(
        TestRepository, MongoRepositoryMixin[mongo_test_model]
    ): ...

    return MongoTestRepository(
        host="mongo-mock",
        port="",
        username="",
        password="",
        database="",
        collection="test",
    )
