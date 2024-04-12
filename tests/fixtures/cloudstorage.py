from abc import ABC
from dataclasses import dataclass

import google.cloud.storage  # type: ignore
import pytest
from cloud_storage_mocker import Mount  # type: ignore
from cloud_storage_mocker import patch as gcs_patch


@pytest.fixture
def cloudstorage_test_model():
    from fractal_repositories.core.entity import Entity

    @dataclass
    class TestModelCloudStorage(Entity):
        id: str
        name: str = "test"
        description: str = "test"

    return TestModelCloudStorage


@pytest.fixture
def cloudstorage_test_repository(cloudstorage_test_model):
    from fractal_repositories.contrib.gcp.cloudstorage.mixins import (
        CloudStorageRepositoryMixin,
    )
    from fractal_repositories.core.repositories import Repository

    class TestRepository(Repository[cloudstorage_test_model], ABC):
        entity = cloudstorage_test_model

    from fractal_repositories.mixins.inmemory_repository_mixin import (
        InMemoryRepositoryMixin,
    )

    class CloudStorageTestRepository(
        TestRepository,
        InMemoryRepositoryMixin[cloudstorage_test_model],
        CloudStorageRepositoryMixin[cloudstorage_test_model],
    ): ...

    with gcs_patch(
        [
            Mount("test", ".", True, True),
        ]
    ):
        client = google.cloud.storage.Client()

        class Settings:
            cloudstorage_client = client

        repository = CloudStorageTestRepository(Settings(), collection="test")

        yield repository
