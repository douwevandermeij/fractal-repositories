"""
Migrate a Mongo collection between ISO-string and native datetimes.

Up to 1.8, :class:`~fractal_repositories.contrib.mongo.mixins.MongoRepositoryMixin`
stored every datetime as the ISO string ``Entity.asdict()`` produces. With
``native_datetimes`` on it stores BSON dates instead, and a collection written
before that has to be converted: filters are built from native datetimes, and
Mongo never compares a date with a string, so an unconverted row is invisible
to every datetime filter.

The conversion runs client side rather than as a ``$dateFromString`` pipeline
update. It parses with the same ``datetime.fromisoformat`` an entity reads the
strings back with, so a value converts to exactly the moment the application
already saw; it needs no MongoDB 4.2 pipeline updates; and it truncates to the
millisecond in the same place the write path does.

Every write is conditional on the field still holding the string it was read
with, so the migration is idempotent and safe to run from several processes at
once: a row converted (or rewritten) by someone else in between is left alone.
"""

import dataclasses
import logging
import types
import typing
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Iterator, List, Optional, Union

from pymongo import UpdateOne

from fractal_repositories.utils.stored_specification import (
    to_native_datetime,
    to_stored_value,
)

logger = logging.getLogger(__name__)

#: Where a completed migration is recorded, one document per collection.
MIGRATIONS_COLLECTION = "fractal_migrations"
#: Identifies this migration in :data:`MIGRATIONS_COLLECTION`.
NATIVE_DATETIMES_MIGRATION = "native-datetimes-v1"

BATCH_SIZE = 1000


@dataclass
class MigrationResult:
    collection: str
    fields: List[str] = field(default_factory=list)
    #: Values rewritten by this run.
    converted: int = 0
    #: Strings that do not parse as a datetime, left as they were.
    unparseable: int = 0
    #: Fields holding datetimes the migration cannot reach, e.g. inside lists.
    skipped_fields: List[str] = field(default_factory=list)


def _unwrap(annotation: Any) -> Any:
    """``Optional[X]`` / ``X | None`` to ``X``; any other union to None."""
    if typing.get_origin(annotation) in (Union, types.UnionType):
        args = [a for a in typing.get_args(annotation) if a is not type(None)]
        return args[0] if len(args) == 1 else None
    return annotation


def _mentions(annotation: Any, target: type) -> bool:
    if annotation is target:
        return True
    return any(_mentions(a, target) for a in typing.get_args(annotation))


def datetime_fields(entity: type, *, _prefix: str = "", _seen=None):
    """The dotted paths of every stored datetime field of ``entity``.

    Returns ``(paths, skipped)``: ``skipped`` are fields that hold datetimes
    somewhere this migration cannot address with a dotted path, such as inside
    a list.
    """
    seen = set() if _seen is None else _seen
    if entity in seen:
        return [], []
    seen = seen | {entity}
    try:
        hints = typing.get_type_hints(entity)
    except Exception:  # unresolvable forward references
        hints = {}
    calculated_fields = getattr(entity, "calculated_fields", None)
    calculated = set(calculated_fields()) if callable(calculated_fields) else set()

    paths: List[str] = []
    skipped: List[str] = []
    for f in dataclasses.fields(entity):
        if f.name in calculated:
            continue
        path = f"{_prefix}{f.name}"
        annotation = hints.get(f.name, f.type)
        kind = _unwrap(annotation)
        if kind is datetime:
            paths.append(path)
        elif isinstance(kind, type) and dataclasses.is_dataclass(kind):
            nested, nested_skipped = datetime_fields(
                kind, _prefix=f"{path}.", _seen=seen
            )
            paths += nested
            skipped += nested_skipped
        elif _mentions(annotation, datetime) or any(
            dataclasses.is_dataclass(a) for a in typing.get_args(annotation)
        ):
            skipped.append(path)
    return paths, skipped


def _get(document: dict, path: str) -> Any:
    value: Any = document
    for part in path.split("."):
        if not isinstance(value, dict):
            return None
        value = value.get(part)
    return value


def _parse(value: str) -> Optional[datetime]:
    try:
        # fromisoformat only accepts a trailing Z from Python 3.11 on.
        parsed = datetime.fromisoformat(
            value[:-1] + "+00:00" if value.endswith("Z") else value
        )
    except ValueError:
        return None
    return to_native_datetime(parsed)


def _batches(cursor, size: int) -> Iterator[list]:
    batch = []
    for document in cursor:
        batch.append(document)
        if len(batch) == size:
            yield batch
            batch = []
    if batch:
        yield batch


def _convert(collection, path: str, *, to_native: bool, result: MigrationResult):
    source_type = "string" if to_native else "date"
    cursor = collection.find({path: {"$type": source_type}}, {"_id": 1, path: 1})
    for batch in _batches(cursor, BATCH_SIZE):
        writes = []
        for document in batch:
            original = _get(document, path)
            if to_native:
                value = _parse(original) if isinstance(original, str) else None
                if value is None:
                    result.unparseable += 1
                    continue
            else:
                if original.tzinfo is None:
                    original_utc = original.replace(tzinfo=timezone.utc)
                else:
                    original_utc = original
                value = to_stored_value(original_utc)
            # Conditional on the value read: a row changed since is not ours.
            writes.append(
                UpdateOne(
                    {"_id": document["_id"], path: original}, {"$set": {path: value}}
                )
            )
        if writes:
            result.converted += _write(collection, writes)


def _write(collection, writes: list) -> int:
    if type(collection).__module__.startswith("mongomock"):
        # mongomock's bulk_write rejects the UpdateOne of current pymongo.
        return sum(
            collection.update_one(w._filter, w._doc).modified_count for w in writes
        )
    return collection.bulk_write(writes, ordered=False).modified_count


def migrate_datetimes(repository, *, reverse: bool = False) -> MigrationResult:
    """Convert ``repository``'s collection to native datetimes (or back).

    Safe to run at any time and any number of times. On success the forward
    migration is recorded in :data:`MIGRATIONS_COLLECTION`, which is what lets
    ``auto_migrate`` skip the scan on later starts; ``reverse`` removes that
    record again.
    """
    collection = repository.collection
    paths, skipped = datetime_fields(repository.entity)
    result = MigrationResult(
        collection=collection.name, fields=paths, skipped_fields=skipped
    )
    for path in paths:
        _convert(collection, path, to_native=not reverse, result=result)

    if skipped:
        logger.warning(
            "Collection %s: datetimes in %s cannot be migrated and stay as they are",
            collection.name,
            ", ".join(skipped),
        )
    if result.unparseable:
        logger.warning(
            "Collection %s: %d value(s) did not parse as a datetime and stay strings",
            collection.name,
            result.unparseable,
        )
    logger.info(
        "Collection %s: %s %d datetime value(s) in %s",
        collection.name,
        "reverted" if reverse else "converted",
        result.converted,
        ", ".join(paths) or "no datetime fields",
    )

    records = repository.db[MIGRATIONS_COLLECTION]
    record_id = f"{collection.name}:{NATIVE_DATETIMES_MIGRATION}"
    if reverse:
        records.delete_one({"_id": record_id})
    else:
        records.update_one(
            {"_id": record_id},
            {
                "$set": {
                    "collection": collection.name,
                    "migration": NATIVE_DATETIMES_MIGRATION,
                    "fields": paths,
                    "converted": result.converted,
                    "unparseable": result.unparseable,
                    "migrated_on": datetime.now(timezone.utc),
                }
            },
            upsert=True,
        )
    return result


def is_migrated(repository) -> bool:
    records = repository.db[MIGRATIONS_COLLECTION]
    record_id = f"{repository.collection.name}:{NATIVE_DATETIMES_MIGRATION}"
    return records.find_one({"_id": record_id}, {"_id": 1}) is not None
