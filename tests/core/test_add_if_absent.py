"""The add-if-absent contract, asserted identically against every backend that
claims to honour it.

The case that matters is recording something exactly once: give a record an id
derived from what it records, and every later attempt to record the same thing
(a retry, a redelivery, a replay) must find it there and add nothing -- also
when two attempts run at the same moment.
"""

import threading
import uuid
from abc import ABC

import pytest
from fractal_specifications.generic.specification import Specification

from tests.fixtures.repositories import AnObject


@pytest.fixture
def mongo_repository():
    from fractal_repositories.contrib.mongo.mixins import MongoRepositoryMixin
    from fractal_repositories.core.repositories import Repository

    class ARepository(Repository[AnObject], ABC):
        entity = AnObject

    class MongoRepository(ARepository, MongoRepositoryMixin[AnObject]): ...

    return MongoRepository(
        host="mongo-mock",
        port="",
        username="",
        password="",
        database="",
        collection=f"ledger-{uuid.uuid4().hex}",
    )


BACKENDS = [
    "inmemory_repository",
    "file_repository_on_disk",
    "sqlite_repository",
    "mongo_repository",
]


@pytest.fixture(params=BACKENDS)
def repository(request):
    return request.getfixturevalue(request.param)


def test_backend_declares_support(repository):
    assert repository.supports_add_if_absent is True


def test_adds_when_the_id_is_free(repository):
    assert repository.add_if_absent(AnObject("1", "first")) is True
    assert repository.find_one(Specification.parse(id="1")).name == "first"


def test_adds_nothing_when_the_id_is_taken(repository):
    repository.add_if_absent(AnObject("1", "first"))

    assert repository.add_if_absent(AnObject("1", "second")) is False
    # The first record stands, untouched.
    assert repository.find_one(Specification.parse(id="1")).name == "first"
    assert repository.count() == 1


def test_a_row_added_the_ordinary_way_also_counts_as_present(repository):
    repository.add(AnObject("1", "via add"))

    assert repository.add_if_absent(AnObject("1", "again")) is False
    assert repository.find_one(Specification.parse(id="1")).name == "via add"


def test_different_ids_are_independent(repository):
    assert repository.add_if_absent(AnObject("1")) is True
    assert repository.add_if_absent(AnObject("2")) is True
    assert repository.count() == 2


@pytest.mark.parametrize(
    "backend", ["inmemory_repository", "file_repository_on_disk", "sqlite_repository"]
)
def test_of_many_concurrent_attempts_exactly_one_wins(request, backend):
    """The race add_if_absent exists for: N threads record the same thing."""
    repository = request.getfixturevalue(backend)
    attempts = 16
    barrier = threading.Barrier(attempts)
    results = []

    def attempt(n):
        barrier.wait()
        results.append(repository.add_if_absent(AnObject("same", f"attempt {n}")))

    threads = [threading.Thread(target=attempt, args=(n,)) for n in range(attempts)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert results.count(True) == 1
    assert results.count(False) == attempts - 1
    assert repository.count() == 1


def test_mongo_creates_a_unique_index_on_id(mongo_repository):
    mongo_repository.add_if_absent(AnObject("1"))
    indexes = mongo_repository.collection.index_information()
    assert indexes["id_unique"]["unique"] is True


def test_mongo_refuses_clearly_when_duplicate_ids_are_already_stored(mongo_repository):
    # Possible today: Mongo's plain add() never checked the id.
    mongo_repository.add(AnObject("dup"))
    mongo_repository.add(AnObject("dup"))

    with pytest.raises(RuntimeError, match="unique index on `id`"):
        mongo_repository.add_if_absent(AnObject("other"))


def test_a_backend_without_support_says_so_rather_than_guessing():
    from fractal_repositories.core.repositories import Repository

    class Unsupported(Repository[AnObject]):
        entity = AnObject

        def add(self, entity): ...
        def update(self, entity, *, upsert=False): ...
        def remove_one(self, specification): ...
        def find_one(self, specification): ...
        def find(self, specification=None, *, offset=0, limit=0, order_by=""): ...
        def count(self, specification=None): ...
        def is_healthy(self): ...

    repository = Unsupported()

    assert repository.supports_add_if_absent is False
    with pytest.raises(NotImplementedError, match="supports_add_if_absent"):
        repository.add_if_absent(AnObject("1"))


# -- wrappers pass it through to the store they wrap ------------------------------


def test_cached_repository_adds_to_the_main_store_and_follows_in_the_cache(
    inmemory_repository,
):
    from fractal_repositories.mixins.inmemory_repository_mixin import (
        InMemoryRepositoryMixin,
    )
    from fractal_repositories.utils.cached_repository import CachedRepository

    class Cache(InMemoryRepositoryMixin[AnObject]):
        entity = AnObject

    class Cached(CachedRepository[AnObject]):
        entity = AnObject

    cache = Cache()
    repository = Cached(main_repository=inmemory_repository, cache_repository=cache)

    assert repository.supports_add_if_absent is True
    assert repository.add_if_absent(AnObject("1", "first")) is True
    assert repository.add_if_absent(AnObject("1", "second")) is False
    assert cache.find_one(Specification.parse(id="1")).name == "first"


def test_memoized_repository_passes_it_through(inmemory_repository):
    from fractal_repositories.utils.memoized_repository import MemoizedRepository

    repository = MemoizedRepository(inmemory_repository)

    assert repository.supports_add_if_absent is True
    assert repository.add_if_absent(AnObject("1")) is True
    assert repository.add_if_absent(AnObject("1")) is False


def test_migrating_repository_checks_the_new_store_only(inmemory_repository):
    from fractal_repositories.mixins.inmemory_repository_mixin import (
        InMemoryRepositoryMixin,
    )
    from fractal_repositories.utils.migrating_repository import MigratingRepository

    class Old(InMemoryRepositoryMixin[AnObject]):
        entity = AnObject

    old = Old()
    old.add(AnObject("1", "only in the old store"))
    repository = MigratingRepository(primary=inmemory_repository, source=old)

    assert repository.supports_add_if_absent is True
    assert repository.add_if_absent(AnObject("1", "new")) is True
    assert inmemory_repository.find_one(Specification.parse(id="1")).name == "new"
