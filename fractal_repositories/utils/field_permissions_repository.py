import copy
import dataclasses
import enum

from fractal_specifications.generic.operators import EqualsSpecification

from fractal_repositories.core.repositories import EntityType, Repository


class OnWriteConflict(enum.Enum):
    RAISE = "raise"
    PRESERVE = "preserve"


class FieldPermissionsRepository(Repository[EntityType]):
    """Wraps any Repository to enforce entity.field_permissions().

    Entities must define a field_permissions() classmethod returning:
        {"field_name": {"read_roles": [...], "write_roles": [...]}}

    roles=None  → transparent (no masking/validation). For internal calls.
    roles=[...] → enforce permissions (even if empty). For API-originated calls.

    A field a caller may not read is hidden in two ways: it comes back as None,
    and a specification that mentions it is refused (find, find_one, count).
    Blanking alone is not enough: filtering on the field and watching which
    records come back reveals its value, and a prefix match recovers it a
    character at a time. The check sees the whole specification, so a role's own
    filter must not reference a field that role cannot read either.
    """

    def __init__(
        self,
        inner: Repository[EntityType],
        *,
        forbidden_exception_class=PermissionError,
        on_write_conflict=OnWriteConflict.RAISE,
    ):
        if not isinstance(on_write_conflict, OnWriteConflict):
            raise ValueError(
                f"on_write_conflict must be a OnWriteConflict member, got {on_write_conflict!r}"
            )
        self.entity = inner.entity
        super().__init__()
        self._inner = inner
        self._forbidden_exception_class = forbidden_exception_class
        self._on_write_conflict = on_write_conflict

    @property
    def _field_permissions(self):
        fp = getattr(self._inner.entity, "field_permissions", None)
        return fp() if callable(fp) else {}

    @staticmethod
    def _field_default(entity, field):
        """Return the effective default for a dataclass field.

        Falls back to ``default_factory()`` when present, or the type's zero
        value (``str()`` → ``""``, ``int()`` → ``0``, …) when neither a
        default nor a factory is defined.
        """
        df = entity.__dataclass_fields__[field]
        if df.default is not dataclasses.MISSING:
            return df.default
        if df.default_factory is not dataclasses.MISSING:
            return df.default_factory()
        return type(getattr(entity, field))()

    def _validate_write_permissions(
        self, entity, field_permissions, roles, stored=None
    ):
        """
        Raise if the caller lacks write permission for any changed field.

        For updates (``stored`` provided), only raises when the field value actually
        changed. For adds (no ``stored``), raises when the field differs from its
        dataclass default.

        Args:
            entity: The entity being written.
            field_permissions: Mapping of field name → permission config.
            roles: The caller's roles.
            stored: The existing entity from the repository, or None for new entities.

        Raises:
            forbidden_exception_class: If a restricted field was modified without
                the required write role.
        """
        for field, p in field_permissions.items():
            write_roles = p.get("write_roles")
            if write_roles is not None and not any(r in write_roles for r in roles):
                if stored is not None:
                    if getattr(entity, field) != getattr(stored, field):
                        raise self._forbidden_exception_class(
                            f"No permission to write field '{field}'"
                        )
                else:
                    default = self._field_default(entity, field)
                    if getattr(entity, field) != default:
                        raise self._forbidden_exception_class(
                            f"No permission to write field '{field}'"
                        )

    def _apply_write_preserve(self, entity, field_permissions, roles, stored=None):
        """
        Silently reset secured fields for callers that lack write permission.

        When ``stored`` is provided (update), restricted fields are copied from
        the stored entity. When ``stored`` is ``None`` (add), they are reset to
        the field's dataclass default (or type zero value if no default exists).

        Args:
            entity: The entity being written (mutated in-place).
            field_permissions: Mapping of field name → permission config.
            roles: The caller's roles.
            stored: The existing stored entity, or ``None`` for new entities.

        Returns:
            The entity with restricted fields reset.
        """
        for field, p in field_permissions.items():
            write_roles = p.get("write_roles")
            if write_roles is not None and not any(r in write_roles for r in roles):
                value = (
                    getattr(stored, field)
                    if stored is not None
                    else self._field_default(entity, field)
                )
                setattr(entity, field, value)
        return entity

    @staticmethod
    def _unreadable_fields(field_permissions, roles):
        """The fields with ``read_roles`` none of which ``roles`` holds."""
        return {
            field
            for field, perms in field_permissions.items()
            if perms.get("read_roles") is not None
            and not any(role in perms["read_roles"] for role in roles)
        }

    def _apply_read_mask(self, entity, field_permissions, roles):
        """
        Blank out fields the caller is not allowed to read.

        Fields without ``read_roles`` defined are always visible. Fields with
        ``read_roles`` are set to ``None`` when none of the caller's roles match.

        Never mutates ``entity``: when there is something to hide it returns a
        shallow copy. The entity may be the one an inner repository keeps --
        MemoizedRepository hands out its cached object -- and masking that in
        place blanked the field for every later reader, and an update built on it
        wrote None over the stored value.

        Args:
            entity: The entity to mask. Left untouched.
            field_permissions: Mapping of field name → permission config.
            roles: The caller's roles.

        Returns:
            ``entity`` itself when nothing is hidden, otherwise a masked copy.
        """
        hidden = [
            field
            for field in self._unreadable_fields(field_permissions, roles)
            if hasattr(entity, field)
        ]
        if not hidden:
            return entity
        masked = copy.copy(entity)
        for field in hidden:
            setattr(masked, field, None)
        return masked

    def _check_specification(self, specification, roles):
        """Refuse a specification that mentions a field ``roles`` cannot read."""
        if roles is None or specification is None:
            return
        unreadable = self._unreadable_fields(self._field_permissions, roles)
        if not unreadable:
            return
        for field in sorted(_specification_fields(specification) & unreadable):
            raise self._forbidden_exception_class(
                f"No permission to filter on field '{field}'"
            )

    def find_one(self, specification, *, roles=None) -> EntityType:
        """
        Find a single entity, optionally masking restricted fields.

        Args:
            specification: Filter criteria for the query.
            roles: Caller's roles. Pass ``None`` to skip masking (internal use).

        Returns:
            The matching entity, with unreadable fields blanked out when roles are provided.

        Raises:
            ObjectNotFoundException: If no entity matches the specification.
            forbidden_exception_class: If the specification mentions a field the
                caller cannot read.
        """
        self._check_specification(specification, roles)
        result = self._inner.find_one(specification)
        if roles is not None:
            return self._apply_read_mask(result, self._field_permissions, roles)
        return result

    def find(
        self,
        specification=None,
        *,
        offset=0,
        limit=0,
        order_by="",
        roles=None,
        **kwargs,
    ):
        """
        Find multiple entities, optionally masking restricted fields.

        Args:
            specification: Filter criteria for the query.
            offset: Number of results to skip.
            limit: Maximum number of results to return (0 = unlimited).
            order_by: Field name to sort by.
            roles: Caller's roles. Pass ``None`` to skip masking (internal use).

        Returns:
            An iterator or list of matching entities, with unreadable fields blanked
            out when roles are provided.

        Raises:
            forbidden_exception_class: If the specification mentions a field the
                caller cannot read.
        """
        self._check_specification(specification, roles)
        results = self._inner.find(
            specification, offset=offset, limit=limit, order_by=order_by
        )
        if roles is None:
            return results
        return [
            self._apply_read_mask(e, self._field_permissions, roles) for e in results
        ]

    def count(self, specification=None, *, roles=None):
        """
        Count entities matching the specification.

        A count answers the same question a filter does, so it gets the same
        check: with ``roles``, a specification on a field the caller cannot read
        is refused.

        Args:
            specification: Filter criteria, or None to count all entities.
            roles: Caller's roles. Pass ``None`` to skip the check (internal use).

        Returns:
            The number of matching entities.

        Raises:
            forbidden_exception_class: If the specification mentions a field the
                caller cannot read.
        """
        self._check_specification(specification, roles)
        return self._inner.count(specification)

    def get(self, id) -> EntityType:
        """
        Find a single entity by ID without read masking.

        Equivalent to calling ``find_one`` with ``roles=None``. Use ``find_one``
        directly with ``roles`` if masking is required.

        Args:
            id: The entity ID to look up.

        Returns:
            The matching entity.

        Raises:
            ObjectNotFoundException: If no entity with the given ID exists.
        """
        return self.find_one(EqualsSpecification("id", id))

    def add(self, entity: EntityType, *, roles=None) -> EntityType:
        """
        Add a new entity, optionally enforcing write permissions.

        When ``on_write_conflict="raise"`` (default), raises if a restricted field
        is set to a non-default value. When ``on_write_conflict="preserve"``,
        restricted fields are silently reset to their dataclass default (or type
        zero value) instead of raising.

        Args:
            entity: The entity to add.
            roles: Caller's roles. Pass ``None`` to skip validation (internal use).

        Returns:
            The added entity.

        Raises:
            forbidden_exception_class: If ``on_write_conflict="raise"`` and a
                restricted field is set to a non-default value without the required
                write role.
        """
        if roles is not None:
            perms = self._field_permissions
            if self._on_write_conflict == OnWriteConflict.PRESERVE:
                entity = self._apply_write_preserve(entity, perms, roles)
            else:
                self._validate_write_permissions(entity, perms, roles)
        return self._inner.add(entity)

    def update(self, entity: EntityType, *, upsert=False, roles=None) -> EntityType:
        """
        Update an entity, optionally enforcing write permissions against stored values.

        When ``roles`` are provided, the stored entity is fetched first so that
        validation can compare new vs. existing field values. If the entity is not
        found (e.g. during an upsert), validation falls back to comparing against
        dataclass defaults.

        The ``on_write_conflict`` setting controls what happens when a caller without
        write permission submits a changed value for a secured field:

        - ``"raise"`` (default): raises ``forbidden_exception_class``.
        - ``"preserve"``: silently restores the stored value, allowing the rest of
          the update to proceed. Useful for PUT-style APIs where the caller sends
          back the full entity including fields they cannot see.

        When upserting a new entity, both modes fall back to add-style validation
        (raise if the secured field differs from its default / zero value).

        Args:
            entity: The entity with updated values.
            upsert: If True, insert the entity when it does not exist yet.
            roles: Caller's roles. Pass ``None`` to skip validation (internal use).

        Returns:
            The updated entity.

        Raises:
            forbidden_exception_class: If ``on_write_conflict="raise"`` and a
                restricted field was changed without the required write role.
        """
        if roles is not None:
            perms = self._field_permissions
            try:
                stored = self._inner.find_one(EqualsSpecification("id", entity.id))
                if self._on_write_conflict == OnWriteConflict.PRESERVE:
                    entity = self._apply_write_preserve(entity, perms, roles, stored)
                else:
                    self._validate_write_permissions(
                        entity, perms, roles, stored=stored
                    )
            except Exception as e:
                if isinstance(e, self._forbidden_exception_class):
                    raise
                # Entity not found (upsert) — fall back to add-style handling
                if self._on_write_conflict == OnWriteConflict.PRESERVE:
                    entity = self._apply_write_preserve(entity, perms, roles)
                else:
                    self._validate_write_permissions(entity, perms, roles)
        return self._inner.update(entity, upsert=upsert)

    @property
    def supports_compare_and_swap(self) -> bool:  # type: ignore[override]
        return self._inner.supports_compare_and_swap

    def compare_and_swap(self, entity, *, expected) -> bool:
        """
        Swap an entity only while the stored row still matches ``expected``.

        No ``roles`` parameter, deliberately: a compare-and-swap resolves a race
        between two writers over a row one of them just read, which is internal
        machinery, not a caller-submitted write. Field permissions are enforced
        where a caller's values enter, on :meth:`add` and :meth:`update`.

        Args:
            entity: The entity to store.
            expected: What must still hold for the stored row.

        Returns:
            True when the swap happened, False when the row had already moved on.
        """
        return self._inner.compare_and_swap(entity, expected=expected)

    @property
    def supports_add_if_absent(self) -> bool:  # type: ignore[override]
        return self._inner.supports_add_if_absent

    def add_if_absent(self, entity, *, roles=None) -> bool:
        """
        Add an entity only if none with its id is stored yet.

        Field permissions apply exactly as on :meth:`add`: this is a caller's
        values entering the store, just with an existence check attached.

        Args:
            entity: The entity to add.
            roles: Caller's roles. Pass ``None`` to skip validation (internal use).

        Returns:
            True when the entity was added, False when one with its id existed.
        """
        if roles is not None:
            perms = self._field_permissions
            if self._on_write_conflict == OnWriteConflict.PRESERVE:
                entity = self._apply_write_preserve(entity, perms, roles)
            else:
                self._validate_write_permissions(entity, perms, roles)
        return self._inner.add_if_absent(entity)

    def remove_one(self, specification):
        """
        Remove a single entity matching the specification. Delegates directly to the inner repository.

        Args:
            specification: Filter criteria to identify the entity to remove.
        """
        self._inner.remove_one(specification)

    def delete(self, id):
        """
        Remove a single entity by ID. Delegates directly to the inner repository.

        Args:
            id: The entity ID to remove.
        """
        self._inner.delete(id)

    def is_healthy(self) -> bool:
        """
        Check if the inner repository connection is healthy.

        Returns:
            True if the inner repository is healthy, False otherwise.
        """
        return self._inner.is_healthy()


def _specification_fields(specification) -> set:
    """Every entity field a specification reads, as top-level names.

    Walks And/Or/Not trees down to the field-value leaves. A nested lookup
    ("address.city", "address__city") counts as its top-level field, since
    that is what a field permission names.
    """
    from fractal_specifications.generic.collections import CollectionSpecification
    from fractal_specifications.generic.operators import (
        FieldValueSpecification,
        NotSpecification,
    )

    if isinstance(specification, CollectionSpecification):
        fields = set()
        for child in specification.specifications:
            fields |= _specification_fields(child)
        return fields
    if isinstance(specification, NotSpecification):
        return _specification_fields(specification.specification)
    if isinstance(specification, FieldValueSpecification):
        name = specification.field
        separator = "__" if "__" in name else "."
        return {name.split(separator)[0]}
    return set()
