"""
Rewrite a specification's values into the shape ``Entity.asdict()`` stores.

Document stores (Mongo, Firestore) persist ``entity.asdict()``, which turns
datetimes, dates, times, decimals, UUIDs and enums into strings or plain
values. A specification built from domain values still carries the originals,
and neither store compares across types: a ``created_on__lt=<datetime>`` filter
never matches a stored ISO string, it silently matches nothing.
"""

from datetime import date, datetime, time, timezone
from decimal import Decimal
from enum import Enum
from typing import Any, Optional
from uuid import UUID

from fractal_specifications.generic.collections import CollectionSpecification
from fractal_specifications.generic.operators import (
    FieldValueSpecification,
    NotSpecification,
)
from fractal_specifications.generic.specification import Specification


def to_native_datetime(value: datetime) -> datetime:
    """A datetime as a store with native, millisecond dates holds it.

    Aware and in UTC, naive values taken to be UTC already, and truncated to
    the millisecond: BSON dates carry no finer precision, so a value written
    with microseconds would read back different, and an equality filter on it
    would never match what was stored.
    """
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    value = value.astimezone(timezone.utc)
    return value.replace(microsecond=value.microsecond // 1000 * 1000)


def to_stored_value(value: Any, *, native_datetimes: bool = False) -> Any:
    """One value as ``Entity.asdict()`` writes it.

    Aware datetimes are normalised to UTC first. The stored strings are
    compared lexicographically, which orders them correctly only when they
    share an offset, and UTC is what entities default to. With
    ``native_datetimes`` the store keeps datetimes as datetimes, and they are
    only normalised by :func:`to_native_datetime`.
    """
    if isinstance(value, (list, tuple, set)):
        return type(value)(
            to_stored_value(v, native_datetimes=native_datetimes) for v in value
        )
    if isinstance(value, Decimal):
        return f"{value:.2f}"
    # datetime before date: datetime is a subclass of date.
    if isinstance(value, datetime):
        if native_datetimes:
            return to_native_datetime(value)
        if value.tzinfo is not None:
            value = value.astimezone(timezone.utc)
        return value.isoformat()
    if isinstance(value, date):
        return value.strftime("%Y-%m-%d")
    if isinstance(value, time):
        return value.isoformat()
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, Enum):
        return value.value
    return value


def to_stored_specification(
    specification: Optional[Specification], *, native_datetimes: bool = False
) -> Optional[Specification]:
    """The specification with every value rewritten by :func:`to_stored_value`.

    Copies rather than mutates: the caller's specification may be reused
    against a backend that holds the domain values themselves.
    """
    if isinstance(specification, FieldValueSpecification):
        stored = type(specification).__new__(type(specification))
        stored.__dict__.update(specification.__dict__)
        stored.value = to_stored_value(
            specification.value, native_datetimes=native_datetimes
        )
        return stored
    if isinstance(specification, CollectionSpecification):
        return type(specification)(
            [
                to_stored_specification(s, native_datetimes=native_datetimes)
                for s in specification.specifications
            ]
        )
    if isinstance(specification, NotSpecification):
        return NotSpecification(
            to_stored_specification(
                specification.specification, native_datetimes=native_datetimes
            )
        )
    return specification
