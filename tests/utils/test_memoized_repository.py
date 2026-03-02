from dataclasses import dataclass

import pytest
from fractal_specifications.generic.specification import Specification

from fractal_repositories.core.entity import Entity
from fractal_repositories.exceptions import ObjectNotFoundException
from fractal_repositories.mixins.inmemory_repository_mixin import (
    InMemoryRepositoryMixin,
)
from fractal_repositories.utils.memoized_repository import MemoizedRepository

# ---------------------------------------------------------------------------
# Entity and inner repo helpers
# ---------------------------------------------------------------------------


@dataclass
class Item(Entity):
    id: str
    name: str = "default"


def make_inner():
    class InnerRepo(InMemoryRepositoryMixin[Item]):
        entity = Item

    return InnerRepo()


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def inner():
    return make_inner()


@pytest.fixture
def repo(inner):
    return MemoizedRepository(inner)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_is_healthy(repo, inner, mocker):
    spy = mocker.spy(inner, "is_healthy")
    assert repo.is_healthy() is True
    assert spy.call_count == 1


def test_find_one(repo):
    repo.add(Item("1", name="Alice"))
    result = repo.find_one(Specification.parse(id="1"))
    assert result.id == "1"
    assert result.name == "Alice"


def test_find_one_not_found(repo):
    with pytest.raises(ObjectNotFoundException):
        repo.find_one(Specification.parse(id="nonexistent"))


def test_find_one_is_cached(repo, inner, mocker):
    repo.add(Item("1", name="Alice"))
    spy = mocker.spy(inner, "find_one")
    spec = Specification.parse(id="1")

    repo.find_one(spec)
    repo.find_one(spec)

    assert spy.call_count == 1


def test_get_uses_cache(repo, inner, mocker):
    repo.add(Item("1", name="Alice"))
    spy = mocker.spy(inner, "find_one")

    repo.get("1")
    repo.get("1")

    assert spy.call_count == 1


def test_find_delegates_directly(repo, inner, mocker):
    repo.add(Item("1"))
    repo.add(Item("2"))
    spy = mocker.spy(inner, "find")

    list(repo.find())
    list(repo.find())

    assert spy.call_count == 2


def test_count_delegates_directly(repo, inner, mocker):
    repo.add(Item("1"))
    spy = mocker.spy(inner, "count")

    repo.count()
    repo.count()

    assert spy.call_count == 2


def test_add_does_not_affect_other_cache_entries(repo, inner, mocker):
    repo.add(Item("1", name="Alice"))
    spec = Specification.parse(id="1")
    repo.find_one(spec)  # populate cache

    spy = mocker.spy(inner, "find_one")
    repo.add(Item("2", name="Bob"))
    repo.find_one(spec)  # served from cache — no inner call

    assert spy.call_count == 0


def test_update_updates_cached_entry_in_place(repo, inner, mocker):
    repo.add(Item("1", name="Alice"))
    spec = Specification.parse(id="1")
    repo.find_one(spec)  # populate cache

    spy = mocker.spy(inner, "find_one")
    repo.update(Item("1", name="Updated"))
    result = repo.find_one(spec)  # served from cache — no inner call

    assert spy.call_count == 0
    assert result.name == "Updated"


def test_remove_one_clears_cache(repo, inner, mocker):
    repo.add(Item("1", name="Alice"))
    repo.add(Item("2", name="Bob"))
    spec = Specification.parse(id="2")
    repo.find_one(spec)  # populate cache

    spy = mocker.spy(inner, "find_one")
    repo.remove_one(Specification.parse(id="1"))
    # spec for id=1 is NOT in _spec_index → preliminary inner.find_one(id=1) (+1),
    # then InMemoryRepositoryMixin.remove_one calls inner.find_one internally (+1).
    # The explicit find_one(spec for id=2) below is served from cache (+0) — total 2.
    repo.find_one(spec)  # served from cache

    assert spy.call_count == 2


def test_delete_clears_cache(repo, inner, mocker):
    repo.add(Item("1", name="Alice"))
    repo.add(Item("2", name="Bob"))
    spec = Specification.parse(id="2")
    repo.find_one(spec)  # populate cache

    spy = mocker.spy(inner, "find_one")
    repo.delete("1")
    # delete → remove_one; spec for id=1 not in _spec_index → preliminary inner.find_one (+1),
    # then InMemoryRepositoryMixin.remove_one calls inner.find_one internally (+1).
    # The explicit find_one(spec for id=2) below is served from cache (+0) — total 2.
    repo.find_one(spec)  # served from cache

    assert spy.call_count == 2


def test_update_only_invalidates_updated_entity(repo, inner, mocker):
    repo.add(Item("1", name="Alice"))
    repo.add(Item("2", name="Bob"))
    spec1 = Specification.parse(id="1")
    spec2 = Specification.parse(id="2")
    repo.find_one(spec1)  # populate cache for id=1
    repo.find_one(spec2)  # populate cache for id=2

    spy = mocker.spy(inner, "find_one")
    repo.update(Item("1", name="Updated"))
    repo.find_one(spec2)  # id=2 still cached — no inner call

    assert spy.call_count == 0


def test_remove_one_only_invalidates_removed_entity(repo, inner, mocker):
    repo.add(Item("1", name="Alice"))
    repo.add(Item("2", name="Bob"))
    spec1 = Specification.parse(id="1")
    spec2 = Specification.parse(id="2")
    repo.find_one(spec1)  # populate cache for id=1
    repo.find_one(spec2)  # populate cache for id=2

    spy = mocker.spy(inner, "find_one")
    repo.remove_one(spec1)
    # spec1 IS in _spec_index → O(1) entity_id lookup, no preliminary inner.find_one,
    # but InMemoryRepositoryMixin.remove_one calls it internally (+1).
    # find_one for id=2 is served from cache (+0) — total 1.
    repo.find_one(spec2)  # id=2 still cached — no extra inner call

    assert spy.call_count == 1


def test_cache_independent_per_instance():
    inner_a = make_inner()
    inner_b = make_inner()
    repo_a = MemoizedRepository(inner_a)
    repo_b = MemoizedRepository(inner_b)

    repo_a.add(Item("1", name="A"))
    repo_b.add(Item("1", name="B"))

    assert repo_a.find_one(Specification.parse(id="1")).name == "A"
    assert repo_b.find_one(Specification.parse(id="1")).name == "B"

    # Mutating one repo's cache does not affect the other
    repo_a.add(Item("2", name="extra"))
    assert repo_b.count() == 1
