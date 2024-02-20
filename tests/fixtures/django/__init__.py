from abc import ABC
from dataclasses import dataclass, field
from typing import List

import pytest
from django.apps import AppConfig  # type: ignore


class DjangoTestsConfig(AppConfig):
    name = "tests.fixtures.django"
    verbose_name = "Django Tests"


@pytest.fixture
def django_settings():
    from django.apps import apps  # type: ignore
    from django.conf import settings  # type: ignore

    apps.ready = True

    if not settings.configured:
        settings.configure(
            DEBUG=True,
            SECRET_KEY="my-secret-key",
            INSTALLED_APPS=[
                "tests.fixtures.django.DjangoTestsConfig",
            ],
            DATABASES={
                "default": {"ENGINE": "django.db.backends.sqlite3", "NAME": ":memory:"}
            },
        )

        apps.set_installed_apps(settings.INSTALLED_APPS)

        from django.core.management import call_command  # type: ignore

        call_command("migrate", "--run-syncdb")


@pytest.fixture
def django_test_model(django_test_sub_model):
    from fractal_repositories.core.entity import Entity

    @dataclass
    class TestModel(Entity):
        id: str
        name: str = "test"
        description: str = "test"
        items: List[django_test_sub_model] = field(default_factory=list)

    return TestModel


@pytest.fixture
def django_test_sub_model():
    from tests.fixtures.django.models import TestSubModel

    return TestSubModel


@pytest.fixture
def django_test_model_dao():
    from tests.fixtures.django.models import TestModel

    return TestModel


@pytest.fixture
def django_test_repository(django_settings, django_test_model, django_test_model_dao):
    from fractal_repositories.contrib.django.mixins import DjangoModelRepositoryMixin
    from fractal_repositories.core.repositories import Repository

    class TestRepository(Repository[django_test_model], ABC):
        entity = django_test_model

    class DjangoTestRepository(
        TestRepository,
        DjangoModelRepositoryMixin[django_test_model],
    ): ...

    django_test_model_dao.objects.all().delete()

    return DjangoTestRepository(django_model=django_test_model_dao)
