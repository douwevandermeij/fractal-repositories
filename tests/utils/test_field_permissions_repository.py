from dataclasses import dataclass

import pytest
from fractal_specifications.generic.specification import Specification

from fractal_repositories.core.entity import Entity
from fractal_repositories.mixins.inmemory_repository_mixin import (
    InMemoryRepositoryMixin,
)
from fractal_repositories.utils.field_permissions_repository import (
    FieldPermissionsRepository,
)

# ---------------------------------------------------------------------------
# Entities
# ---------------------------------------------------------------------------


@dataclass
class SecureObject(Entity):
    id: str
    name: str = "default"
    secret: str = "secret_default"

    @classmethod
    def field_permissions(cls):
        return {
            "secret": {
                "read_roles": ["admin"],
                "write_roles": ["admin"],
            }
        }


@dataclass
class PlainObject(Entity):
    id: str
    name: str = "default"


# ---------------------------------------------------------------------------
# Inner repo helpers
# ---------------------------------------------------------------------------


def make_secure_inner():
    class InnerRepo(InMemoryRepositoryMixin[SecureObject]):
        entity = SecureObject

    return InnerRepo()


def make_plain_inner():
    class InnerRepo(InMemoryRepositoryMixin[PlainObject]):
        entity = PlainObject

    return InnerRepo()


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def inner():
    return make_secure_inner()


@pytest.fixture
def repo(inner):
    return FieldPermissionsRepository(inner)


@pytest.fixture
def plain_inner():
    return make_plain_inner()


@pytest.fixture
def plain_repo(plain_inner):
    return FieldPermissionsRepository(plain_inner)


# ---------------------------------------------------------------------------
# 1. Transparent delegation (no roles / entity without field_permissions)
# ---------------------------------------------------------------------------


def test_is_healthy(repo):
    assert repo.is_healthy()


def test_count_empty(repo):
    assert repo.count() == 0


def test_count_with_entities(repo):
    repo.add(SecureObject("1"))
    repo.add(SecureObject("2"))
    assert repo.count() == 2


def test_count_with_spec(repo):
    repo.add(SecureObject("1"))
    repo.add(SecureObject("2"))
    assert repo.count(Specification.parse(id="1")) == 1


def test_find_one_no_roles(repo):
    repo.add(SecureObject("1", secret="top_secret"))
    result = repo.find_one(Specification.parse(id="1"), roles=None)
    assert result.secret == "top_secret"


def test_find_no_roles(repo):
    repo.add(SecureObject("1", secret="top_secret"))
    repo.add(SecureObject("2", secret="also_secret"))
    results = list(repo.find(roles=None))
    assert all(r.secret != "" for r in results)


def test_get_returns_unmasked(repo):
    repo.add(SecureObject("1", secret="top_secret"))
    result = repo.get("1")
    assert result.secret == "top_secret"


def test_add_no_roles(repo):
    entity = repo.add(SecureObject("1", name="test", secret="any_value"), roles=None)
    assert entity.id == "1"
    assert repo.count() == 1


def test_update_no_roles(repo):
    repo.add(SecureObject("1", name="old"))
    repo.update(SecureObject("1", name="new"), roles=None)
    assert repo.get("1").name == "new"


def test_remove_one(repo):
    repo.add(SecureObject("1"))
    repo.remove_one(Specification.parse(id="1"))
    assert repo.count() == 0


def test_delete(repo):
    repo.add(SecureObject("1"))
    repo.delete("1")
    assert repo.count() == 0


def test_plain_object_is_healthy(plain_repo):
    assert plain_repo.is_healthy()


def test_plain_object_add_no_error(plain_repo):
    plain_repo.add(PlainObject("1", name="test"), roles=["user"])
    assert plain_repo.count() == 1


def test_plain_object_find_one_no_error(plain_repo):
    plain_repo.add(PlainObject("1", name="test"))
    result = plain_repo.find_one(Specification.parse(id="1"), roles=["user"])
    assert result.name == "test"


def test_plain_object_find_no_error(plain_repo):
    plain_repo.add(PlainObject("1"))
    plain_repo.add(PlainObject("2"))
    results = list(plain_repo.find(roles=["user"]))
    assert len(results) == 2


def test_plain_object_update_no_error(plain_repo):
    plain_repo.add(PlainObject("1", name="old"))
    plain_repo.update(PlainObject("1", name="new"), roles=["user"])
    assert plain_repo.get("1").name == "new"


def test_plain_object_remove_one_no_error(plain_repo):
    plain_repo.add(PlainObject("1"))
    plain_repo.remove_one(Specification.parse(id="1"))
    assert plain_repo.count() == 0


def test_plain_object_delete_no_error(plain_repo):
    plain_repo.add(PlainObject("1"))
    plain_repo.delete("1")
    assert plain_repo.count() == 0


# ---------------------------------------------------------------------------
# 2. Read masking
# ---------------------------------------------------------------------------


def test_find_one_admin_sees_secret(repo):
    repo.add(SecureObject("1", secret="top_secret"))
    result = repo.find_one(Specification.parse(id="1"), roles=["admin"])
    assert result.secret == "top_secret"


def test_find_one_user_secret_blanked(repo):
    repo.add(SecureObject("1", secret="top_secret"))
    result = repo.find_one(Specification.parse(id="1"), roles=["user"])
    assert result.secret == ""


def test_find_admin_sees_secret(repo):
    repo.add(SecureObject("1", secret="s1"))
    repo.add(SecureObject("2", secret="s2"))
    results = list(repo.find(roles=["admin"]))
    assert all(r.secret != "" for r in results)


def test_find_user_secret_blanked(repo):
    repo.add(SecureObject("1", secret="s1"))
    repo.add(SecureObject("2", secret="s2"))
    results = list(repo.find(roles=["user"]))
    assert all(r.secret == "" for r in results)


def test_find_one_roles_none_no_masking(repo):
    repo.add(SecureObject("1", secret="top_secret"))
    result = repo.find_one(Specification.parse(id="1"), roles=None)
    assert result.secret == "top_secret"


# ---------------------------------------------------------------------------
# 3. Write validation — add
# ---------------------------------------------------------------------------


def test_add_admin_can_set_secret(repo):
    entity = repo.add(SecureObject("1", secret="my_secret"), roles=["admin"])
    assert entity.secret == "my_secret"


def test_add_user_with_default_secret_allowed(repo):
    entity = repo.add(SecureObject("1", secret="secret_default"), roles=["user"])
    assert entity.id == "1"


def test_add_user_with_changed_secret_raises(repo):
    with pytest.raises(PermissionError):
        repo.add(SecureObject("1", secret="hacked"), roles=["user"])


# ---------------------------------------------------------------------------
# 4. Write validation — update
# ---------------------------------------------------------------------------


def test_update_admin_can_change_secret(repo):
    repo.add(SecureObject("1", secret="old"))
    repo.update(SecureObject("1", secret="new"), roles=["admin"])
    assert repo.get("1").secret == "new"


def test_update_user_unchanged_secret_allowed(repo):
    repo.add(SecureObject("1", secret="original"))
    repo.update(SecureObject("1", name="updated", secret="original"), roles=["user"])
    assert repo.get("1").name == "updated"


def test_update_user_changed_secret_raises(repo):
    repo.add(SecureObject("1", secret="original"))
    with pytest.raises(PermissionError):
        repo.update(SecureObject("1", secret="changed"), roles=["user"])


def test_update_upsert_new_entity_default_secret_allowed(repo):
    repo.update(
        SecureObject("99", secret="secret_default"), upsert=True, roles=["user"]
    )
    assert repo.get("99").id == "99"


def test_update_upsert_new_entity_changed_secret_raises(repo):
    with pytest.raises(PermissionError):
        repo.update(SecureObject("99", secret="hacked"), upsert=True, roles=["user"])


# ---------------------------------------------------------------------------
# 5. Custom forbidden_exception_class
# ---------------------------------------------------------------------------


class CustomForbiddenError(Exception):
    pass


def test_custom_exception_on_add():
    inner = make_secure_inner()
    repo = FieldPermissionsRepository(
        inner, forbidden_exception_class=CustomForbiddenError
    )
    with pytest.raises(CustomForbiddenError):
        repo.add(SecureObject("1", secret="hacked"), roles=["user"])


def test_custom_exception_on_update():
    inner = make_secure_inner()
    inner.add(SecureObject("1", secret="original"))
    repo = FieldPermissionsRepository(
        inner, forbidden_exception_class=CustomForbiddenError
    )
    with pytest.raises(CustomForbiddenError):
        repo.update(SecureObject("1", secret="changed"), roles=["user"])


def test_custom_exception_not_permission_error():
    inner = make_secure_inner()
    repo = FieldPermissionsRepository(
        inner, forbidden_exception_class=CustomForbiddenError
    )
    with pytest.raises(CustomForbiddenError):
        repo.add(SecureObject("1", secret="hacked"), roles=["user"])
    # ensure it is NOT a PermissionError
    try:
        repo.add(SecureObject("2", secret="hacked"), roles=["user"])
    except CustomForbiddenError:
        pass
    except PermissionError:
        pytest.fail("Expected CustomForbiddenError, got PermissionError")
