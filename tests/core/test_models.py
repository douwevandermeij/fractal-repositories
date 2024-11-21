from dataclasses import dataclass
from datetime import date, datetime, timezone
from decimal import Decimal
from typing import List

import pytest


@pytest.fixture
def decimal():
    return Decimal(1.1)


@pytest.fixture
def now():
    return datetime.now(timezone.utc)


@pytest.fixture
def model_instance(now, decimal):
    from fractal_repositories.core.entity import Entity

    @dataclass
    class M(Entity):
        string: str = "name"
        number: int = 1
        string_list: List[str] = None
        now: datetime = None
        decimal_number: Decimal = decimal

        def __post_init__(self):
            if not self.string_list:
                self.string_list = ["a", "b"]
            if not self.now:
                self.now = now

    return M(id="1")


@pytest.fixture
def nested_model_instance(model_instance):
    from fractal_repositories.core.entity import Entity

    @dataclass
    class M(Entity):
        nested_list: List = None

        def __post_init__(self):
            if not self.nested_list:
                self.nested_list = [model_instance]

    return M(id="1")


def test_model(model_instance, now, decimal):
    assert model_instance.asdict(use_timezone_z=False) == {
        "id": "1",
        "string": "name",
        "number": 1,
        "string_list": ["a", "b"],
        "now": now.isoformat(),
        "decimal_number": f"{decimal:.2f}",
    }


def test_model_update(model_instance, now, decimal):
    some_new_values = {
        "id": "1",
        "string": "new_name",
        "number": 2,
        "string_list": ["c", "d"],
    }
    assert model_instance.update(some_new_values).asdict() == {
        **some_new_values,
        "now": now.isoformat(),
        "decimal_number": f"{decimal:.2f}",
    }


def test_model_skip_types(model_instance, now, decimal):
    assert model_instance.asdict(
        skip_types=(
            list,
            datetime,
            Decimal,
        )
    ) == {
        "id": "1",
        "string": "name",
        "number": 1,
        "string_list": ["a", "b"],
        "now": now,
        "decimal_number": decimal,
    }


def test_model_nested(nested_model_instance, now, decimal):
    assert nested_model_instance.asdict(use_timezone_z=False) == {
        "id": "1",
        "nested_list": [
            {
                "id": "1",
                "string": "name",
                "number": 1,
                "string_list": ["a", "b"],
                "now": now.isoformat(),
                "decimal_number": f"{decimal:.2f}",
            }
        ],
    }


def test_model_nested_skip_types(nested_model_instance, model_instance, now, decimal):
    m = nested_model_instance.asdict(
        skip_types=(
            list,
            datetime,
            Decimal,
        )
    )[
        "nested_list"
    ][0]
    assert type(m) == type(model_instance)
    assert m.now == now


def test_model_nested_skip_types_no_list(nested_model_instance, now, decimal):
    assert nested_model_instance.asdict(
        skip_types=(
            datetime,
            Decimal,
        )
    ) == {
        "id": "1",
        "nested_list": [
            {
                "id": "1",
                "string": "name",
                "number": 1,
                "string_list": ["a", "b"],
                "now": now,
                "decimal_number": decimal,
            }
        ],
    }


@pytest.mark.parametrize(
    "input, output",
    [
        ({"id": "1", "d": "", "dt": ""}, {"id": "1", "d": None, "dt": None}),
        ({"id": "1", "d": None, "dt": None}, {"id": "1", "d": None, "dt": None}),
        (
            {"id": "1", "d": "2020-01-01T00:00:00", "dt": "2020-01-01T00:00:00"},
            {"id": "1", "d": "2020-01-01", "dt": "2020-01-01T00:00:00"},
        ),
        (
            {"id": "1", "d": "2020-01-01", "dt": "2020-01-01"},
            {"id": "1", "d": "2020-01-01", "dt": "2020-01-01T00:00:00"},
        ),
        (
            {
                "id": "1",
                "d": "2020-01-01",
                "dt": "2020-01-01T07:43:22.086238+00:00",
            },
            {
                "id": "1",
                "d": "2020-01-01",
                "dt": "2020-01-01T07:43:22.086238+00:00",
            },
        ),
    ],
)
def test_pydantic_dataclass_date_datetime(input, output):
    from pydantic.dataclasses import dataclass

    from fractal_repositories.core.entity import Entity

    @dataclass
    class M(Entity):
        d: date = None
        dt: datetime = None

    assert M.clean(**input).asdict() == output
