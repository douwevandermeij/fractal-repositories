from dataclasses import dataclass

import pytest
from fractal_specifications.generic.specification import Specification

from fractal_repositories.core.entity import Entity
from fractal_repositories.mixins.inmemory_repository_mixin import (
    InMemoryRepositoryMixin,
)
from fractal_repositories.utils.field_permissions_repository import (
    FieldPermissionsRepository,
    OnWriteConflict,
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


@dataclass
class NoDefaultSecureObject(Entity):
    """Secured field with no dataclass default — falls back to type zero value."""

    id: str
    secret: str  # no default

    @classmethod
    def field_permissions(cls):
        return {
            "secret": {
                "read_roles": ["admin"],
                "write_roles": ["admin"],
            }
        }


# ---------------------------------------------------------------------------
# Inner repo helpers
# ---------------------------------------------------------------------------


def make_secure_inner():
    class InnerRepo(InMemoryRepositoryMixin[SecureObject]):
        entity = SecureObject

    return InnerRepo()


def make_no_default_inner():
    class InnerRepo(InMemoryRepositoryMixin[NoDefaultSecureObject]):
        entity = NoDefaultSecureObject

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


# ---------------------------------------------------------------------------
# 6. No-default secured field — MISSING fallback to type zero value (add only)
# ---------------------------------------------------------------------------


def test_no_default_user_can_add_with_zero_value():
    """Non-admin may add when the secured field equals the type zero value ("")."""
    inner = make_no_default_inner()
    repo = FieldPermissionsRepository(inner)
    repo.add(NoDefaultSecureObject("1", secret=""), roles=["user"])
    assert repo.count() == 1


def test_no_default_user_cannot_add_with_non_zero_value():
    """Non-admin is blocked when the secured field is set to any non-empty value."""
    inner = make_no_default_inner()
    repo = FieldPermissionsRepository(inner)
    with pytest.raises(PermissionError):
        repo.add(NoDefaultSecureObject("1", secret="hacked"), roles=["user"])


def test_no_default_admin_can_add_with_any_value():
    inner = make_no_default_inner()
    repo = FieldPermissionsRepository(inner)
    repo.add(NoDefaultSecureObject("1", secret="admin_value"), roles=["admin"])
    assert repo.get("1").secret == "admin_value"


def test_no_default_user_cannot_update_zero_to_non_zero():
    """The MISSING fallback does NOT apply to updates — changing from "" is blocked."""
    inner = make_no_default_inner()
    repo = FieldPermissionsRepository(inner)
    inner.add(NoDefaultSecureObject("1", secret=""))
    with pytest.raises(PermissionError):
        repo.update(NoDefaultSecureObject("1", secret="changed"), roles=["user"])


def test_no_default_user_can_update_unchanged_zero_value():
    """Non-admin update is allowed when the secured field is unchanged."""
    inner = make_no_default_inner()
    repo = FieldPermissionsRepository(inner)
    inner.add(NoDefaultSecureObject("1", secret=""))
    repo.update(NoDefaultSecureObject("1", secret=""), roles=["user"])
    assert repo.get("1").secret == ""


# ---------------------------------------------------------------------------
# 7. on_write_conflict=OnWriteConflict.PRESERVE
# ---------------------------------------------------------------------------


def test_invalid_on_write_conflict_raises():
    inner = make_secure_inner()
    with pytest.raises(ValueError):
        FieldPermissionsRepository(
            inner, on_write_conflict="preserve"
        )  # string, not enum


def test_preserve_user_can_update_unprotected_field_after_admin_sets_secret():
    """Core use case: user updates an unprotected field; admin-set secret is preserved."""
    inner = make_secure_inner()
    repo = FieldPermissionsRepository(inner, on_write_conflict=OnWriteConflict.PRESERVE)
    inner.add(SecureObject("1", name="original", secret="admin_value"))
    # User reads back masked secret ("") and submits the full entity
    repo.update(SecureObject("1", name="updated", secret=""), roles=["user"])
    stored = repo.get("1")
    assert stored.name == "updated"
    assert stored.secret == "admin_value"  # silently preserved


def test_preserve_user_submitting_changed_secret_is_silently_ignored():
    """Even if the user submits a non-empty secret, it is dropped, not raised."""
    inner = make_secure_inner()
    repo = FieldPermissionsRepository(inner, on_write_conflict=OnWriteConflict.PRESERVE)
    inner.add(SecureObject("1", secret="admin_value"))
    repo.update(SecureObject("1", secret="hacked"), roles=["user"])
    assert repo.get("1").secret == "admin_value"


def test_preserve_admin_can_still_update_secret():
    """preserve mode does not restrict callers that DO have write permission."""
    inner = make_secure_inner()
    repo = FieldPermissionsRepository(inner, on_write_conflict=OnWriteConflict.PRESERVE)
    inner.add(SecureObject("1", secret="old"))
    repo.update(SecureObject("1", secret="new"), roles=["admin"])
    assert repo.get("1").secret == "new"


def test_preserve_upsert_new_entity_secret_reset_to_default():
    """Upsert-as-create: non-default secret is silently reset to the dataclass default."""
    inner = make_secure_inner()
    repo = FieldPermissionsRepository(inner, on_write_conflict=OnWriteConflict.PRESERVE)
    repo.update(SecureObject("99", secret="hacked"), upsert=True, roles=["user"])
    assert repo.get("99").secret == "secret_default"


def test_preserve_add_user_secret_reset_to_default():
    """add: non-default secret is silently reset to the dataclass default."""
    inner = make_secure_inner()
    repo = FieldPermissionsRepository(inner, on_write_conflict=OnWriteConflict.PRESERVE)
    repo.add(SecureObject("1", secret="hacked"), roles=["user"])
    assert repo.get("1").secret == "secret_default"


def test_preserve_add_admin_secret_stored_as_submitted():
    """add: admin's submitted value is stored unchanged."""
    inner = make_secure_inner()
    repo = FieldPermissionsRepository(inner, on_write_conflict=OnWriteConflict.PRESERVE)
    repo.add(SecureObject("1", secret="admin_value"), roles=["admin"])
    assert repo.get("1").secret == "admin_value"


def test_preserve_add_no_default_field_reset_to_zero_value():
    """add: secured field with no dataclass default is reset to type zero value ("")."""
    inner = make_no_default_inner()
    repo = FieldPermissionsRepository(inner, on_write_conflict=OnWriteConflict.PRESERVE)
    repo.add(NoDefaultSecureObject("1", secret="hacked"), roles=["user"])
    assert repo.get("1").secret == ""
