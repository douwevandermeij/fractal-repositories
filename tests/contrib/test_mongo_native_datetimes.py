import os
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import List, Optional

import mongomock
import pytest
from fractal_specifications.generic.specification import Specification

from fractal_repositories.contrib.mongo.migrations import (
    MIGRATIONS_COLLECTION,
    datetime_fields,
    is_migrated,
    migrate_datetimes,
)
from fractal_repositories.contrib.mongo.mixins import MongoRepositoryMixin
from fractal_repositories.core.entity import Entity, Model

START = datetime(2026, 9, 22, tzinfo=timezone.utc)


@dataclass
class Window(Model):
    opens: Optional[datetime] = None


@dataclass
class Timed(Entity):
    id: str
    name: str = ""
    created_on: Optional[datetime] = None
    window: Optional[Window] = None
    history: List[datetime] = field(default_factory=list)
    derived: Optional[datetime] = None

    @staticmethod
    def calculated_fields():
        return ["derived"]


@pytest.fixture
def client():
    # MONGO_TEST_URI runs these against a real server, which is the only way
    # to exercise the bulk_write path mongomock cannot take.
    if uri := os.environ.get("MONGO_TEST_URI"):
        from pymongo import MongoClient

        real = MongoClient(uri)
        real.drop_database("db")
        yield real
        real.drop_database("db")
    else:
        yield mongomock.MongoClient()


def repository(client, **kwargs):
    class TimedRepository(MongoRepositoryMixin[Timed]):
        entity = Timed

    return TimedRepository(client=client, database="db", collection="timed", **kwargs)


def raw(client, id):
    return client["db"]["timed"].find_one({"id": id})


def ids(entities):
    return sorted(e.id for e in entities)


def test_off_by_default_keeps_strings(client):
    legacy = repository(client)
    legacy.add(Timed(id="1", created_on=START))

    assert raw(client, "1")["created_on"] == "2026-09-22T00:00:00+00:00"


def test_stores_and_reads_native_utc_milliseconds(client):
    native = repository(client, native_datetimes=True)
    local = datetime(2026, 9, 22, 2, 0, 0, 123456, tzinfo=timezone(timedelta(hours=2)))
    native.add(Timed(id="1", created_on=local, window=Window(opens=local)))

    stored = raw(client, "1")
    assert isinstance(stored["created_on"], datetime)
    assert isinstance(stored["window"]["opens"], datetime)

    read = native.find_one(Specification.parse(id="1"))
    assert read.created_on == datetime(
        2026, 9, 22, 0, 0, 0, 123000, tzinfo=timezone.utc
    )
    assert read.created_on.tzinfo is not None


def test_filters_use_native_datetimes(client):
    native = repository(client, native_datetimes=True)
    for hours in (-3, 2, 10, 26):
        native.add(Timed(id=str(hours), created_on=START + timedelta(hours=hours)))
    window = Specification.parse(
        created_on__gte=START, created_on__lt=START + timedelta(days=1)
    )

    assert ids(native.find(window)) == ["10", "2"]
    assert native.count(window) == 2
    assert native.find_one(Specification.parse(created_on__lt=START)).id == "-3"
    assert [
        e.id
        for e in native.find(
            Specification.parse(created_on__lt=START + timedelta(days=1)),
            limit=1,
            order_by="-created_on",
        )
    ] == ["10"]


def test_equality_survives_millisecond_truncation(client):
    native = repository(client, native_datetimes=True)
    moment = START + timedelta(microseconds=123456)
    entity = Timed(id="1", created_on=moment)
    native.add(entity)

    # The caller still holds the microsecond value it wrote.
    assert native.find_one(Specification.parse(created_on=moment)).id == "1"
    assert native.compare_and_swap(
        Timed(id="1", name="swapped", created_on=moment),
        expected=Specification.parse(created_on=moment),
    )
    assert raw(client, "1")["name"] == "swapped"


def _legacy_rows(client):
    legacy = repository(client)
    legacy.add(Timed(id="-3", created_on=START - timedelta(hours=3)))
    legacy.add(
        Timed(
            id="2",
            created_on=START + timedelta(hours=2, microseconds=654321),
            window=Window(opens=START),
            history=[START],
        )
    )
    collection = client["db"]["timed"]
    collection.insert_one({"id": "zulu", "created_on": "2026-09-22T10:00:00Z"})
    collection.insert_one({"id": "naive", "created_on": "2026-09-22T11:00:00"})
    collection.insert_one({"id": "junk", "created_on": "not a date"})


def test_auto_migrates_on_first_use(client):
    _legacy_rows(client)
    native = repository(client, native_datetimes=True)

    window = Specification.parse(
        created_on__gte=START, created_on__lt=START + timedelta(days=1)
    )
    assert ids(native.find(window)) == ["2", "naive", "zulu"]

    assert isinstance(raw(client, "2")["created_on"], datetime)
    assert isinstance(raw(client, "2")["window"]["opens"], datetime)
    # Datetimes inside lists cannot be addressed and are left alone.
    assert raw(client, "2")["history"] == ["2026-09-22T00:00:00+00:00"]
    assert raw(client, "junk")["created_on"] == "not a date"
    assert raw(client, "naive")["created_on"] == datetime(2026, 9, 22, 11)
    assert raw(client, "2")["created_on"].microsecond == 654000
    assert is_migrated(native)


def test_recorded_migration_is_not_rerun(client, mocker):
    _legacy_rows(client)
    repository(client, native_datetimes=True).count()

    spy = mocker.patch(
        "fractal_repositories.contrib.mongo.migrations.migrate_datetimes"
    )
    repository(client, native_datetimes=True).count()

    spy.assert_not_called()


def test_auto_migrate_off_leaves_it_to_the_caller(client):
    _legacy_rows(client)
    native = repository(client, native_datetimes=True, auto_migrate=False)

    assert native.count(Specification.parse(created_on__gte=START)) == 0

    result = migrate_datetimes(native)

    assert result.converted == 5
    assert result.unparseable == 1
    assert result.fields == ["created_on", "window.opens"]
    assert result.skipped_fields == ["history"]
    assert native.count(Specification.parse(created_on__gte=START)) == 3


def test_migration_is_idempotent(client):
    _legacy_rows(client)
    native = repository(client, native_datetimes=True, auto_migrate=False)

    assert migrate_datetimes(native).converted == 5
    assert migrate_datetimes(native).converted == 0


def test_reverse_migration_restores_strings(client):
    _legacy_rows(client)
    native = repository(client, native_datetimes=True)
    native.count()

    result = migrate_datetimes(native, reverse=True)

    assert result.converted == 5
    assert not is_migrated(native)
    assert client["db"][MIGRATIONS_COLLECTION].count_documents({}) == 0
    legacy = repository(client)
    assert raw(client, "zulu")["created_on"] == "2026-09-22T10:00:00+00:00"
    assert ids(
        legacy.find(
            Specification.parse(
                created_on__gte=START, created_on__lt=START + timedelta(days=1)
            )
        )
    ) == ["2", "naive", "zulu"]


def test_conversion_skips_rows_changed_since_read(client, mocker):
    from fractal_repositories.contrib.mongo import migrations

    _legacy_rows(client)
    native = repository(client, native_datetimes=True, auto_migrate=False)
    real_write = migrations._write

    def change_then_write(collection, writes):
        # Another writer replaces the value between the read and the write.
        collection.update_one(
            {"id": "zulu"}, {"$set": {"created_on": "2026-09-23T00:00:00+00:00"}}
        )
        return real_write(collection, writes)

    mocker.patch.object(migrations, "_write", side_effect=change_then_write)
    result = migrations.migrate_datetimes(native)

    assert raw(client, "zulu")["created_on"] == "2026-09-23T00:00:00+00:00"
    assert result.converted == 4


def test_datetime_fields_follow_type_hints():
    @dataclass
    class Unions(Entity):
        id: str
        pipe: datetime | None = None
        optional: Optional[datetime] = None
        plain: datetime = START
        ambiguous: datetime | str = ""
        nested: Window | None = None

    paths, skipped = datetime_fields(Unions)

    assert paths == ["pipe", "optional", "plain", "nested.opens"]
    assert skipped == ["ambiguous"]
    assert datetime_fields(Timed) == (["created_on", "window.opens"], ["history"])
