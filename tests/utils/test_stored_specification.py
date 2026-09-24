from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal
from enum import Enum
from uuid import UUID

from fractal_specifications.generic.specification import Specification

from fractal_repositories.core.entity import Entity
from fractal_repositories.utils.stored_specification import (
    to_stored_specification,
    to_stored_value,
)


class Colour(Enum):
    RED = "red"


@dataclass
class Everything(Entity):
    id: str
    at: datetime
    on: date
    time_of_day: time
    amount: Decimal
    ref: UUID
    colour: Colour


def test_values_match_what_asdict_stores():
    entity = Everything(
        id="1",
        at=datetime(2026, 9, 22, 5, 30, 1, 250, tzinfo=timezone.utc),
        on=date(2026, 9, 22),
        time_of_day=time(5, 30),
        amount=Decimal("1.5"),
        ref=UUID("12345678-1234-5678-1234-567812345678"),
        colour=Colour.RED,
    )

    stored = entity.asdict()

    for field in ("at", "on", "time_of_day", "amount", "ref", "colour"):
        assert to_stored_value(getattr(entity, field)) == stored[field], field


def test_aware_datetimes_are_normalised_to_utc():
    local = datetime(2026, 9, 22, tzinfo=timezone(timedelta(hours=2)))

    assert to_stored_value(local) == "2026-09-21T22:00:00+00:00"


def test_specification_is_copied_not_mutated():
    moment = datetime(2026, 9, 22, tzinfo=timezone.utc)
    specification = Specification.parse(
        name="x", created_at__gte=moment, id__in=[UUID(int=1)]
    )

    stored = to_stored_specification(specification)

    assert [s.value for s in stored.to_collection()] == [
        "x",
        "2026-09-22T00:00:00+00:00",
        ["00000000-0000-0000-0000-000000000001"],
    ]
    assert specification.to_collection()[1].value == moment
    assert to_stored_specification(None) is None
