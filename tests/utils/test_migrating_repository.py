"""MigratingRepository: switch stores without migrating first.

`primary` stands for the new store, `source` for the old one.
"""

import pytest
from fractal_specifications.generic.specification import Specification

from fractal_repositories.exceptions import ObjectNotFoundException
from fractal_repositories.utils.migrating_repository import MigratingRepository
from tests.fixtures import C


class Clock:
    def __init__(self):
        self.now = 0.0

    def __call__(self):
        return self.now


@pytest.fixture
def new(inmemory_c_repository):
    return inmemory_c_repository


@pytest.fixture
def old(another_inmemory_c_repository):
    return another_inmemory_c_repository


def _repo(new, old, **kwargs):
    return MigratingRepository(primary=new, source=old, **kwargs)


def test_an_entity_only_in_the_old_store_is_moved_when_asked_for(new, old):
    old.add(C(1, "a", 1))

    entity = _repo(new, old).find_one(Specification.parse(id=1))

    assert entity.name == "a"
    assert new.entities[1].name == "a"


def test_it_is_found_by_any_field_not_only_the_id(new, old):
    old.add(C(1, "a", 1))

    assert _repo(new, old).find_one(Specification.parse(name="a")).id == 1
    assert 1 in new.entities


def test_find_moves_what_matches(new, old):
    old.add(C(1, "a", 1))
    old.add(C(2, "b", 2))

    found = list(_repo(new, old).find(Specification.parse(name="b")))

    assert [e.id for e in found] == [2]
    assert list(new.entities) == [2]


def test_an_unfiltered_find_copies_nothing(new, old):
    old.add(C(1, "a", 1))

    assert list(_repo(new, old).find()) == []
    assert new.entities == {}


def test_missing_everywhere_is_not_found(new, old):
    with pytest.raises(ObjectNotFoundException):
        _repo(new, old).find_one(Specification.parse(id=9))


def test_the_new_store_wins_when_nothing_refreshes(new, old):
    new.add(C(1, "new", 1))
    old.add(C(1, "old", 1))

    assert _repo(new, old).find_one(Specification.parse(id=1)).name == "new"


def test_a_change_in_the_old_store_arrives_after_refresh_after(new, old):
    clock = Clock()
    repo = _repo(new, old, refresh_after=60, clock=clock)
    old.add(C(1, "a", 1))
    repo.find_one(Specification.parse(id=1))

    old.update(C(1, "renamed", 1))
    clock.now = 30
    assert repo.find_one(Specification.parse(id=1)).name == "a"

    clock.now = 61
    assert repo.find_one(Specification.parse(id=1)).name == "renamed"
    assert new.entities[1].name == "renamed"


def test_an_entity_the_old_store_does_not_have_is_left_alone(new, old):
    clock = Clock()
    repo = _repo(new, old, refresh_after=0, clock=clock)
    new.add(C(1, "created in the new store", 1))

    assert repo.find_one(Specification.parse(id=1)).name == "created in the new store"


def test_same_decides_what_counts_as_a_change(new, old):
    clock = Clock()
    repo = _repo(
        new, old, refresh_after=0, clock=clock, same=lambda a, b: a.name == b.name
    )
    new.add(C(1, "a", 1, extra="kept"))
    old.add(C(1, "a", 1, extra="ignored"))

    assert repo.find_one(Specification.parse(id=1)).extra == "kept"
    assert new.entities[1].extra == "kept"


def test_an_old_store_outage_does_not_fail_a_read(new, old, monkeypatch):
    clock = Clock()
    repo = _repo(new, old, refresh_after=0, clock=clock)
    new.add(C(1, "a", 1))

    def down(*args, **kwargs):
        raise RuntimeError("firestore unavailable")

    monkeypatch.setattr(old, "find_one", down)
    monkeypatch.setattr(old, "find", down)

    assert repo.find_one(Specification.parse(id=1)).name == "a"
    assert list(repo.find(Specification.parse(name="nobody"))) == []
    with pytest.raises(ObjectNotFoundException):
        repo.find_one(Specification.parse(id=2))


def test_writes_go_to_the_new_store_only(new, old):
    repo = _repo(new, old)

    repo.add(C(1, "a", 1))
    repo.update(C(1, "b", 1))

    assert new.entities[1].name == "b"
    assert old.entities == {}
    repo.remove_one(Specification.parse(id=1))
    assert new.entities == {}


def test_count_is_the_new_store_s(new, old):
    old.add(C(1, "a", 1))

    assert _repo(new, old).count() == 0


def test_backfill_copies_everything(new, old):
    old.add(C(1, "a", 1))
    old.add(C(2, "b", 2))
    new.add(C(2, "stale", 2))

    assert _repo(new, old).backfill() == 2
    assert {e.id: e.name for e in new.entities.values()} == {1: "a", 2: "b"}


def test_it_passes_the_new_store_s_not_found_exception(new, old):
    repo = _repo(new, old)

    assert repo.object_not_found_exception_class is getattr(
        new, "object_not_found_exception_class", None
    )
