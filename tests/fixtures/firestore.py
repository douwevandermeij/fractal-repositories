from abc import ABC
from dataclasses import dataclass
from datetime import date, datetime

import pytest


@pytest.fixture
def firestore_test_model(now):
    from fractal_repositories.core.entity import Entity

    @dataclass
    class TestModelFirestore(Entity):
        id: str
        name: str = "test"
        description: str = "test"
        created_on: date = now
        created_at: datetime = now

    return TestModelFirestore


@pytest.fixture
def firebase_client_mock(mocker):
    from mockfirestore import MockFirestore  # type: ignore

    mocker.patch("firebase_admin.firestore.client", lambda: MockFirestore())


@pytest.fixture
def firestore_test_repository(firestore_test_model, firebase_client_mock):
    from fractal_repositories.contrib.gcp.firestore.mixins import (
        FirestoreRepositoryMixin,
    )
    from fractal_repositories.core.repositories import Repository

    class TestRepository(Repository[firestore_test_model], ABC):
        entity = firestore_test_model

    class FirestoreTestRepository(
        TestRepository, FirestoreRepositoryMixin[firestore_test_model]
    ): ...

    repository = FirestoreTestRepository(collection="test")

    yield repository

    repository.collection._data.clear()
