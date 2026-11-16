import copy
from dataclasses import dataclass

import pytest
from fractal_specifications.generic.collections import (
    AndSpecification,
    OrSpecification,
)
from fractal_specifications.generic.operators import (
    EqualsSpecification,
    NotSpecification,
    RegexStringMatchSpecification,
)
from fractal_specifications.generic.specification import Specification

from fractal_repositories.core.entity import Entity
from fractal_repositories.mixins.inmemory_repository_mixin import (
    InMemoryRepositoryMixin,
)
from fractal_repositories.utils.field_permissions_repository import (
    FieldPermissionsRepository,
    OnWriteConflict,
)
from fractal_repositories.utils.memoized_repository import MemoizedRepository

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
    assert all(r.secret is not None for r in results)


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
    assert result.secret is None


def test_find_admin_sees_secret(repo):
    repo.add(SecureObject("1", secret="s1"))
    repo.add(SecureObject("2", secret="s2"))
    results = list(repo.find(roles=["admin"]))
    assert all(r.secret is not None for r in results)


def test_find_user_secret_blanked(repo):
    repo.add(SecureObject("1", secret="s1"))
    repo.add(SecureObject("2", secret="s2"))
    results = list(repo.find(roles=["user"]))
    assert all(r.secret is None for r in results)


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
    # User reads back masked secret (None) and submits the full entity
    repo.update(SecureObject("1", name="updated", secret=None), roles=["user"])
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


# ---------------------------------------------------------------------------
# compare_and_swap
# ---------------------------------------------------------------------------


def test_supports_compare_and_swap_follows_the_inner_repository(repo):
    assert repo.supports_compare_and_swap is True


def test_compare_and_swap_delegates(repo):
    repo.add(SecureObject("1", name="first", secret="s"))

    assert repo.compare_and_swap(
        SecureObject("1", name="second", secret="s"),
        expected=Specification.parse(name="first"),
    )
    assert repo.find_one(Specification.parse(id="1")).name == "second"


def test_compare_and_swap_reports_a_lost_race(repo):
    repo.add(SecureObject("1", name="first", secret="s"))
    repo.compare_and_swap(
        SecureObject("1", name="winner", secret="s"),
        expected=Specification.parse(name="first"),
    )

    assert not repo.compare_and_swap(
        SecureObject("1", name="loser", secret="s"),
        expected=Specification.parse(name="first"),
    )
    assert repo.find_one(Specification.parse(id="1")).name == "winner"


# ---------------------------------------------------------------------------
# 9. A read mask never changes the entity it is handed
# ---------------------------------------------------------------------------


def test_masking_leaves_the_stored_entity_alone(inner, repo):
    """The in-memory store hands out the object it keeps; masking that in place
    blanked the stored value for everyone after the first restricted read."""
    repo.add(SecureObject("1", secret="top_secret"))

    assert repo.find_one(Specification.parse(id="1"), roles=["user"]).secret is None
    list(repo.find(roles=["user"]))

    assert inner.get("1").secret == "top_secret"
    assert repo.find_one(Specification.parse(id="1"), roles=["admin"]).secret == (
        "top_secret"
    )


def test_an_entity_with_nothing_to_hide_is_handed_on_as_is(repo):
    repo.add(SecureObject("1", secret="top_secret"))

    stored = repo.find_one(Specification.parse(id="1"))

    assert repo.find_one(Specification.parse(id="1"), roles=["admin"]) is stored


class _FreshCopies(InMemoryRepositoryMixin[SecureObject]):
    """A store like a database: every read is a new object."""

    entity = SecureObject

    def find_one(self, specification):
        return copy.deepcopy(super().find_one(specification))

    def find(self, specification=None, **kwargs):
        return [copy.deepcopy(e) for e in super().find(specification, **kwargs)]


def test_a_restricted_read_does_not_poison_a_memoized_cache():
    """The stack generated apps use: permissions over a memoizing cache over the
    store. The cache hands out its own object, so an in-place mask blanked the
    field for every later reader, and an admin editing another field then wrote
    None over the real value."""
    store = _FreshCopies()
    store.add(SecureObject("1", name="Ann", secret="top_secret"))
    repo = FieldPermissionsRepository(
        MemoizedRepository(store), on_write_conflict=OnWriteConflict.PRESERVE
    )
    by_id = Specification.parse(id="1")
    repo.find_one(by_id, roles=["admin"])  # warm the cache

    assert repo.find_one(by_id, roles=["user"]).secret is None
    assert repo.find_one(by_id, roles=["admin"]).secret == "top_secret"
    assert repo.find_one(by_id).secret == "top_secret"

    edited = repo.find_one(by_id, roles=["admin"])
    edited.name = "Ann B"
    repo.update(edited, roles=["admin"])

    assert store.find_one(by_id).secret == "top_secret"


# ---------------------------------------------------------------------------
# 10. No filtering on a field the caller cannot read
# ---------------------------------------------------------------------------


@pytest.fixture
def two(repo):
    repo.add(SecureObject("1", name="Ann", secret="ann-secret"))
    repo.add(SecureObject("2", name="Bob", secret="bob-secret"))
    return repo


@pytest.mark.parametrize(
    "specification",
    [
        EqualsSpecification("secret", "ann-secret"),
        RegexStringMatchSpecification("secret", "^b"),
        AndSpecification(
            [EqualsSpecification("name", "Ann"), EqualsSpecification("secret", "x")]
        ),
        OrSpecification(
            [
                RegexStringMatchSpecification("name", "zzz"),
                RegexStringMatchSpecification("secret", "^a"),
            ]
        ),
        NotSpecification(EqualsSpecification("secret", "x")),
        EqualsSpecification("secret.inner", "x"),
        EqualsSpecification("secret__inner", "x"),
    ],
    ids=["equals", "regex", "and", "or", "not", "dotted", "double-underscore"],
)
def test_a_filter_on_an_unreadable_field_is_refused(two, specification):
    """Blanking the value is not enough when the caller can still filter on it:
    which records come back tells it the value, and a prefix match recovers it
    a character at a time."""
    with pytest.raises(PermissionError, match="secret"):
        list(two.find(specification, roles=["user"]))
    with pytest.raises(PermissionError, match="secret"):
        two.find_one(specification, roles=["user"])
    with pytest.raises(PermissionError, match="secret"):
        two.count(specification, roles=["user"])


def test_a_caller_who_may_read_the_field_can_filter_on_it(two):
    spec = EqualsSpecification("secret", "ann-secret")

    assert [e.id for e in two.find(spec, roles=["admin"])] == ["1"]
    assert two.find_one(spec, roles=["admin"]).id == "1"
    assert two.count(spec, roles=["admin"]) == 1


def test_internal_calls_are_not_checked(two):
    spec = EqualsSpecification("secret", "ann-secret")

    assert [e.id for e in two.find(spec)] == ["1"]
    assert two.count(spec) == 1


def test_filtering_on_readable_fields_still_works_for_everyone(two):
    spec = EqualsSpecification("name", "Bob")

    found = list(two.find(spec, roles=["user"]))

    assert [(e.id, e.secret) for e in found] == [("2", None)]
    assert two.count(spec, roles=["user"]) == 1


def test_the_refusal_uses_the_configured_exception(inner):
    repo = FieldPermissionsRepository(
        inner, forbidden_exception_class=CustomForbiddenError
    )
    repo.add(SecureObject("1", secret="s"))

    with pytest.raises(CustomForbiddenError):
        list(repo.find(EqualsSpecification("secret", "s"), roles=["user"]))
