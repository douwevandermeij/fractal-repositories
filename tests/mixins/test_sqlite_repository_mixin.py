import json
from dataclasses import dataclass
from typing import Optional

import pytest
from fractal_specifications.generic.specification import Specification

from fractal_repositories.core.entity import Entity
from fractal_repositories.exceptions import ObjectNotFoundException
from fractal_repositories.mixins.sqlite_repository_mixin import SqliteRepositoryMixin
from tests.fixtures.repositories import AnObject


def test_is_healthy(sqlite_repository):
    assert sqlite_repository.is_healthy()


def test_add(sqlite_repository, an_object):
    sqlite_repository.add(an_object)

    assert sqlite_repository.count() == 1
    assert sqlite_repository.find_one(Specification.parse(id=an_object.id)) == an_object


def test_add_last_write_wins(sqlite_repository, an_object):
    sqlite_repository.add(an_object)
    an_object.name = "rewritten"
    sqlite_repository.add(an_object)

    assert sqlite_repository.count() == 1
    assert sqlite_repository.find_one(Specification.parse(id=an_object.id)).name == (
        "rewritten"
    )


def test_update(sqlite_repository, an_object):
    sqlite_repository.add(an_object)

    an_object.name = "update"
    sqlite_repository.update(an_object)

    assert sqlite_repository.count() == 1
    assert sqlite_repository.find_one(Specification.parse(id=an_object.id)).name == (
        "update"
    )


def test_update_upsert(sqlite_repository, an_object):
    sqlite_repository.update(an_object, upsert=True)

    assert sqlite_repository.count() == 1
    assert sqlite_repository.find_one(Specification.parse(id=an_object.id)) == an_object


def test_update_upsert_ignore(sqlite_repository, an_object):
    with pytest.raises(ObjectNotFoundException):
        sqlite_repository.update(an_object)

    assert sqlite_repository.count() == 0


def test_remove_one(sqlite_repository, an_object):
    sqlite_repository.add(an_object)

    sqlite_repository.remove_one(Specification.parse(id=an_object.id))

    assert sqlite_repository.count() == 0


def test_remove_one_not_found(sqlite_repository, an_object):
    with pytest.raises(ObjectNotFoundException):
        sqlite_repository.remove_one(Specification.parse(id=an_object.id))


def test_find_one(sqlite_repository, an_object):
    sqlite_repository.add(an_object)

    assert sqlite_repository.find_one(Specification.parse(id=an_object.id)) == an_object


def test_find_one_not_found(sqlite_repository):
    with pytest.raises(ObjectNotFoundException):
        sqlite_repository.find_one(Specification.parse(id="nope"))


def test_find(sqlite_repository, an_object):
    sqlite_repository.add(an_object)

    assert len(list(sqlite_repository.find())) == 1


def test_find_reverse(sqlite_repository, an_object, another_object):
    sqlite_repository.add(an_object)
    sqlite_repository.add(another_object)

    assert [i.id for i in sqlite_repository.find(order_by="id")] == [
        an_object.id,
        another_object.id,
    ]
    assert [i.id for i in sqlite_repository.find(order_by="-id")] == [
        another_object.id,
        an_object.id,
    ]


def test_find_limit(sqlite_repository, an_object, another_object):
    sqlite_repository.add(an_object)
    sqlite_repository.add(another_object)

    assert len(list(sqlite_repository.find())) == 2
    assert len(list(sqlite_repository.find(limit=1))) == 1


def test_find_with_specification(sqlite_repository, an_object):
    sqlite_repository.add(an_object)

    assert len(list(sqlite_repository.find(Specification.parse(id=an_object.id)))) == 1


def test_find_with_specification_empty(sqlite_repository, an_object):
    sqlite_repository.add(an_object)

    assert len(list(sqlite_repository.find(Specification.parse(id="2")))) == 0


def test_persists_across_instances(sqlite_repository, an_object):
    sqlite_repository.add(an_object)

    # A second repository over the same file sees the committed data — the DB,
    # not an in-process dict, is the source of truth.
    twin = type(sqlite_repository)(root_dir=sqlite_repository.root_dir)
    assert twin.find_one(Specification.parse(id=an_object.id)) == an_object


def test_no_in_memory_store(sqlite_repository, an_object):
    # SQLite is the sole source of truth: there is no vestigial in-memory dict.
    sqlite_repository.add(an_object)
    assert not hasattr(sqlite_repository, "entities")


def test_find_one_uses_indexed_id_lookup(sqlite_repository, an_object, mocker):
    # An id-equality spec must hit the PK with a WHERE clause, not scan the table.
    sqlite_repository.add(an_object)
    prop = mocker.patch.object(
        type(sqlite_repository), "_get_entities", new_callable=mocker.PropertyMock
    )
    prop.side_effect = AssertionError("id lookup must not scan")

    assert sqlite_repository.get(an_object.id) == an_object


def test_find_one_by_id_cross_type_does_not_match(sqlite_repository):
    from dataclasses import dataclass

    from fractal_repositories.core.entity import Entity
    from fractal_repositories.mixins.sqlite_repository_mixin import (
        SqliteRepositoryMixin,
    )

    @dataclass
    class IntEntity(Entity):
        id: int

    class IntRepo(SqliteRepositoryMixin[IntEntity]):
        entity = IntEntity

    repo = IntRepo(root_dir=sqlite_repository.root_dir)
    repo.add(IntEntity(42))

    # Stored id is int 42; querying with the string "42" must not match, exactly
    # like Python-side type-strict equality — the PK index only narrows the
    # candidate, is_satisfied_by makes the final call.
    assert repo.get(42).id == 42
    with pytest.raises(ObjectNotFoundException):
        repo.get("42")


def test_count_no_spec_uses_sql(sqlite_repository, an_object, another_object, mocker):
    sqlite_repository.add(an_object)
    sqlite_repository.add(another_object)
    prop = mocker.patch.object(
        type(sqlite_repository), "_get_entities", new_callable=mocker.PropertyMock
    )
    prop.side_effect = AssertionError("count() must not scan")

    assert sqlite_repository.count() == 2


def test_count_with_spec_filters_in_python(sqlite_repository, an_object):
    sqlite_repository.add(an_object)

    assert sqlite_repository.count(Specification.parse(id=an_object.id)) == 1
    assert sqlite_repository.count(Specification.parse(id="absent")) == 0


def test_delete_by_id(sqlite_repository, an_object):
    sqlite_repository.add(an_object)

    sqlite_repository.delete(an_object.id)

    assert sqlite_repository.count() == 0


def test_delete_by_id_not_found(sqlite_repository):
    with pytest.raises(ObjectNotFoundException):
        sqlite_repository.delete("nope")


@dataclass
class Item(Entity):
    id: str
    n: int = 0
    opt: Optional[int] = None
    status: str = "new"


@pytest.fixture
def item_repository(tmp_path):
    class ItemRepository(SqliteRepositoryMixin[Item]):
        entity = Item

    repo = ItemRepository(root_dir=str(tmp_path))
    repo.add(Item("a", n=1, opt=None, status="new"))
    repo.add(Item("b", n=5, opt=7, status="done"))
    repo.add(Item("c", n=9, opt=None, status="done"))
    return repo


def _ids(entities):
    return sorted(e.id for e in entities)


def _forbid_scan(mocker, repository):
    """Make any access to ``_get_entities`` fail, proving the SQL path was taken."""
    prop = mocker.patch.object(
        type(repository), "_get_entities", new_callable=mocker.PropertyMock
    )
    prop.side_effect = AssertionError("expected SQL pushdown, not a full scan")


def test_find_pushes_filter_into_sql(item_repository, mocker):
    from fractal_specifications.generic.operators import EqualsSpecification

    _forbid_scan(mocker, item_repository)

    found = list(item_repository.find(EqualsSpecification("status", "done")))

    assert _ids(found) == ["b", "c"]


def test_count_pushes_filter_into_sql(item_repository, mocker):
    from fractal_specifications.generic.operators import EqualsSpecification

    _forbid_scan(mocker, item_repository)

    assert item_repository.count(EqualsSpecification("status", "done")) == 2


def test_find_in_and_range(item_repository):
    from fractal_specifications.generic.operators import (
        GreaterThanSpecification,
        InSpecification,
    )

    assert _ids(item_repository.find(InSpecification("status", ["new", "done"]))) == [
        "a",
        "b",
        "c",
    ]
    assert _ids(item_repository.find(GreaterThanSpecification("n", 4))) == ["b", "c"]


def test_find_and_or(item_repository):
    from fractal_specifications.generic.collections import (
        AndSpecification,
        OrSpecification,
    )
    from fractal_specifications.generic.operators import (
        EqualsSpecification,
        GreaterThanSpecification,
    )

    spec = AndSpecification(
        [EqualsSpecification("status", "done"), GreaterThanSpecification("n", 6)]
    )
    assert _ids(item_repository.find(spec)) == ["c"]

    spec = OrSpecification(
        [EqualsSpecification("status", "new"), GreaterThanSpecification("n", 8)]
    )
    assert _ids(item_repository.find(spec)) == ["a", "c"]


def test_find_is_none(item_repository):
    from fractal_specifications.generic.operators import IsNoneSpecification

    assert _ids(item_repository.find(IsNoneSpecification("opt"))) == ["a", "c"]


def test_find_not_equals_includes_null_rows(item_repository):
    # Python: opt != 7 is True for the null rows too; the SQL pushdown must agree.
    from fractal_specifications.generic.operators import NotEqualsSpecification

    assert _ids(item_repository.find(NotEqualsSpecification("opt", 7))) == ["a", "c"]


def test_range_on_null_field_excludes_without_raising(item_repository):
    # Rows a and c have opt=None. A range query excludes them in SQL rather than
    # raising TypeError as the in-memory path would.
    from fractal_specifications.generic.operators import GreaterThanSpecification

    assert _ids(item_repository.find(GreaterThanSpecification("opt", 0))) == ["b"]


def test_unmapped_spec_falls_back_to_python(item_repository):
    from fractal_specifications.generic.operators import ContainsSpecification

    # ContainsSpecification cannot be pushed to SQL (the builder raises), so a
    # correct result here can only come from the Python-scan fallback.
    found = list(item_repository.find(ContainsSpecification("status", "on")))

    assert _ids(found) == ["b", "c"]  # "done" contains "on"


def test_unmapped_count_and_remove_fall_back(item_repository):
    from fractal_specifications.generic.operators import ContainsSpecification

    assert item_repository.count(ContainsSpecification("status", "on")) == 2
    item_repository.remove_one(ContainsSpecification("status", "on"))
    assert _ids(item_repository.find()) == ["a"]


def test_remove_one_by_spec_uses_sql(item_repository):
    from fractal_specifications.generic.operators import EqualsSpecification

    item_repository.remove_one(EqualsSpecification("status", "done"))

    assert _ids(item_repository.find()) == ["a"]


def test_remove_one_by_spec_not_found_raises(item_repository):
    from fractal_specifications.generic.operators import EqualsSpecification

    with pytest.raises(ObjectNotFoundException):
        item_repository.remove_one(EqualsSpecification("status", "absent"))


def _write_raw_row(repository, row_id: str, payload: dict) -> None:
    with repository._connect() as conn:
        conn.execute(
            f'INSERT OR REPLACE INTO "{repository._table}" (id, data) VALUES (?, ?)',
            (row_id, json.dumps(payload)),
        )


def test_ignores_removed_fields_on_read(sqlite_repository):
    # A row written when the entity still had a now-removed field deserializes
    # fine — from_dict drops the unknown key.
    _write_raw_row(sqlite_repository, "1", {"id": "1", "name": "ok", "gone": "stale"})

    found = sqlite_repository.find_one(Specification.parse(id="1"))
    assert found == AnObject("1", "ok")


def test_skips_unbuildable_rows(sqlite_repository, an_object, caplog):
    # Rows that cannot deserialize into the current entity are skipped with a
    # warning, not raised: a row missing the required `id` field, and a row
    # whose JSON is not a mapping at all.
    sqlite_repository.add(an_object)
    _write_raw_row(sqlite_repository, "no-id", {"nonsense": True})
    _write_raw_row(sqlite_repository, "notamap", json.loads("42"))

    found = list(sqlite_repository.find())

    ids = {e.id for e in found}
    assert ids == {an_object.id}
    assert any("Skipping stale row" in r.message for r in caplog.records)
