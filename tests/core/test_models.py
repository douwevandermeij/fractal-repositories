from dataclasses import dataclass
from datetime import date, datetime, time, timezone
from decimal import Decimal
from enum import Enum
from typing import List
from uuid import UUID, uuid4

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
    assert type(m) is type(model_instance)
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


def test_model_with_time_field():
    """Test that time fields are properly converted to isoformat."""
    from fractal_repositories.core.entity import Entity

    @dataclass
    class M(Entity):
        id: str
        meeting_time: time

    test_time = time(14, 30, 45)
    model = M(id="1", meeting_time=test_time)

    result = model.asdict()
    assert result["meeting_time"] == test_time.isoformat()
    assert result["meeting_time"] == "14:30:45"


def test_model_with_uuid_field():
    """Test that UUID fields are properly converted to strings."""
    from fractal_repositories.core.entity import Entity

    @dataclass
    class M(Entity):
        user_id: UUID
        name: str

    test_uuid = uuid4()
    model = M(id="1", user_id=test_uuid, name="John")

    result = model.asdict()
    assert result["user_id"] == str(test_uuid)
    assert isinstance(result["user_id"], str)
    assert result["name"] == "John"


def test_model_with_uuid_skip_type():
    """Test that UUID fields are not converted when in skip_types."""
    from fractal_repositories.core.entity import Entity

    @dataclass
    class M(Entity):
        user_id: UUID
        name: str

    test_uuid = uuid4()
    model = M(id="1", user_id=test_uuid, name="John")

    result = model.asdict(skip_types=[UUID])
    assert result["user_id"] == test_uuid
    assert isinstance(result["user_id"], UUID)
    assert result["name"] == "John"


def test_model_with_uuid_list():
    """Test that lists of UUIDs are properly converted."""
    from fractal_repositories.core.entity import Entity

    @dataclass
    class M(Entity):
        tag_ids: List[UUID]

    uuid1 = uuid4()
    uuid2 = uuid4()
    model = M(id="1", tag_ids=[uuid1, uuid2])

    result = model.asdict()
    assert result["tag_ids"] == [str(uuid1), str(uuid2)]
    assert all(isinstance(uid, str) for uid in result["tag_ids"])


def test_model_with_enum_field():
    """Test that Enum fields are properly converted to their values."""
    from fractal_repositories.core.entity import Entity

    class Status(Enum):
        ACTIVE = "active"
        INACTIVE = "inactive"
        PENDING = "pending"

    @dataclass
    class M(Entity):
        name: str
        status: Status

    model = M(id="1", name="John", status=Status.ACTIVE)

    result = model.asdict()
    assert result["status"] == "active"
    assert result["status"] == Status.ACTIVE.value
    assert isinstance(result["status"], str)


def test_model_with_enum_skip_type():
    """Test that Enum fields are not converted when in skip_types."""
    from fractal_repositories.core.entity import Entity

    class Status(Enum):
        ACTIVE = "active"
        INACTIVE = "inactive"

    @dataclass
    class M(Entity):
        name: str
        status: Status

    model = M(id="1", name="John", status=Status.ACTIVE)

    result = model.asdict(skip_types=[Enum])
    assert result["status"] == Status.ACTIVE
    assert isinstance(result["status"], Status)


def test_model_with_int_enum():
    """Test that integer Enums are properly converted."""
    from fractal_repositories.core.entity import Entity

    class Priority(Enum):
        LOW = 1
        MEDIUM = 2
        HIGH = 3

    @dataclass
    class M(Entity):
        title: str
        priority: Priority

    model = M(id="1", title="Task", priority=Priority.HIGH)

    result = model.asdict()
    assert result["priority"] == 3
    assert result["priority"] == Priority.HIGH.value
    assert isinstance(result["priority"], int)


def test_model_with_enum_list():
    """Test that lists of Enums are properly converted."""
    from fractal_repositories.core.entity import Entity

    class Tag(Enum):
        URGENT = "urgent"
        REVIEW = "review"
        DONE = "done"

    @dataclass
    class M(Entity):
        tags: List[Tag]

    model = M(id="1", tags=[Tag.URGENT, Tag.REVIEW])

    result = model.asdict()
    assert result["tags"] == ["urgent", "review"]
    assert all(isinstance(tag, str) for tag in result["tags"])


def test_model_with_uuid_and_enum():
    """Test that UUID and Enum work together in the same model."""
    from fractal_repositories.core.entity import Entity

    class Status(Enum):
        ACTIVE = "active"
        INACTIVE = "inactive"

    @dataclass
    class M(Entity):
        user_id: UUID
        status: Status
        name: str

    test_uuid = uuid4()
    model = M(id="1", user_id=test_uuid, status=Status.ACTIVE, name="John")

    result = model.asdict()
    assert result["user_id"] == str(test_uuid)
    assert result["status"] == "active"
    assert result["name"] == "John"


def test_model_with_nested_uuid_and_enum():
    """Test that nested models with UUID and Enum are properly converted."""
    from fractal_repositories.core.entity import Entity

    class Role(Enum):
        ADMIN = "admin"
        USER = "user"

    @dataclass
    class User(Entity):
        user_id: UUID
        role: Role

    @dataclass
    class Organization(Entity):
        users: List[User]

    uuid1 = uuid4()
    uuid2 = uuid4()
    user1 = User(id="u1", user_id=uuid1, role=Role.ADMIN)
    user2 = User(id="u2", user_id=uuid2, role=Role.USER)
    org = Organization(id="org1", users=[user1, user2])

    result = org.asdict()
    assert result["users"][0]["user_id"] == str(uuid1)
    assert result["users"][0]["role"] == "admin"
    assert result["users"][1]["user_id"] == str(uuid2)
    assert result["users"][1]["role"] == "user"
