from dataclasses import dataclass, fields
from datetime import date, datetime, time
from decimal import Decimal
from enum import Enum
from typing import Any, Dict
from uuid import UUID


@dataclass
class Model:
    """
    Base model class providing serialization and deserialization capabilities.

    This class is designed to be used with Python's @dataclass decorator and provides
    utilities for converting models to and from dictionaries, with special handling for
    common types like dates, times, decimals, and nested models.

    Example:
        @dataclass
        class User(Model):
            name: str
            email: str
            created_at: datetime

        user = User.from_dict({"name": "John", "email": "john@example.com", "created_at": datetime.now()})
        user_dict = user.asdict()
    """

    @classmethod
    def clean(cls, **kwargs):
        """
        Create an instance from kwargs, filtering out fields not in the dataclass definition.

        This method is useful for creating instances from untrusted or incomplete data,
        as it will only use kwargs that correspond to actual dataclass fields. Date and
        datetime fields that are None or empty are excluded unless explicitly provided.

        Args:
            **kwargs: Arbitrary keyword arguments to construct the model instance.

        Returns:
            An instance of the class with only valid fields populated.

        Example:
            @dataclass
            class User(Model):
                name: str
                email: str

            # Extra fields are ignored
            user = User.clean(name="John", email="john@example.com", extra="ignored")
            # user.name == "John", user.email == "john@example.com"
        """
        field_names = {
            f.name
            for f in fields(cls)
            if f.type not in (date, datetime) or kwargs.get(f.name)
        }
        return cls(**{k: v for k, v in kwargs.items() if k in field_names})  # NOQA

    @classmethod
    def from_dict(cls, data):
        """
        Create an instance from a dictionary.

        This is an alias for the clean() method, providing a more semantic name
        when deserializing from dictionary data.

        Args:
            data: Dictionary containing field values.

        Returns:
            An instance of the class.

        Example:
            user = User.from_dict({"name": "John", "email": "john@example.com"})
        """
        return cls.clean(**data)

    def update(self, model: Dict):
        """
        Create a new instance with updated field values.

        This method does not modify the current instance but returns a new instance
        with the updated values merged with the current values.

        Args:
            model: Dictionary of field values to update.

        Returns:
            A new instance with the updated values.

        Example:
            user = User(name="John", email="john@example.com")
            updated_user = user.update({"email": "newemail@example.com"})
            # updated_user.name == "John", updated_user.email == "newemail@example.com"
            # original user is unchanged
        """
        current = self.asdict()
        current.update(model)
        return self.from_dict(current)

    def asdict(self, *, skip_types=None, use_timezone_z=False):
        """
        Convert the model instance to a dictionary with serialized values.

        This method handles conversion of complex types to JSON-serializable formats:
        - Nested Model/Entity instances are recursively converted
        - Lists are recursively processed
        - Decimal values are formatted to 2 decimal places
        - date values are formatted as "YYYY-MM-DD"
        - time values are formatted as ISO format
        - datetime values are formatted as ISO format (optionally with 'Z' suffix)

        Args:
            skip_types: Optional list of types to skip serialization for.
                       If a type is in this list, the original value is kept.
            use_timezone_z: If True, replace "+00:00" with "Z" in datetime ISO strings.

        Returns:
            Dictionary representation of the model with serialized values.

        Example:
            user = User(name="John", created_at=datetime(2023, 1, 1, 12, 0, 0))
            user_dict = user.asdict()
            # {"name": "John", "created_at": "2023-01-01T12:00:00"}

            # Skip datetime serialization
            user_dict = user.asdict(skip_types=[datetime])
            # {"name": "John", "created_at": <datetime object>}

            # Use Z suffix for UTC timezone
            user_dict = user.asdict(use_timezone_z=True)
            # {"name": "John", "created_at": "2023-01-01T12:00:00Z"}
        """
        if skip_types is None:
            skip_types = []
        field_names = {
            f.name for f in fields(self) if f.name not in self.calculated_fields()
        }

        def _asdict(v):
            if v is None:
                return None
            if isinstance(v, (Model, Entity)):
                return v.asdict(skip_types=skip_types, use_timezone_z=use_timezone_z)
            elif isinstance(v, dict) and dict not in skip_types:
                return {k: _asdict(val) for k, val in v.items()}
            elif isinstance(v, (list, tuple)) and type(v) not in skip_types:
                result = [_asdict(i) for i in v]
                return type(v)(result) if isinstance(v, tuple) else result
            elif isinstance(v, Decimal) and Decimal not in skip_types:
                return f"{v:.2f}"
                # Important: Check datetime BEFORE date (datetime is subclass of date)
            elif type(v) is datetime and datetime not in skip_types:
                return (
                    v.isoformat().replace("+00:00", "Z")
                    if use_timezone_z
                    else v.isoformat()
                )
            elif type(v) is date and date not in skip_types:
                return v.strftime("%Y-%m-%d")
            elif type(v) is time and time not in skip_types:
                return v.isoformat()
            elif isinstance(v, UUID) and UUID not in skip_types:
                return str(v)
            elif isinstance(v, Enum) and Enum not in skip_types:
                return v.value
            return v

        ret = {k: _asdict(v) for k, v in self.__dict__.items() if k in field_names}
        return ret

    @staticmethod
    def calculated_fields():
        """
        Return a list of field names that are calculated and should be excluded from serialization.

        Override this method in subclasses to specify which fields are calculated/derived
        and should not be included in the asdict() output.

        Returns:
            List of field names to exclude from serialization. Defaults to empty list.

        Example:
            @dataclass
            class User(Model):
                first_name: str
                last_name: str

                @property
                def full_name(self):
                    return f"{self.first_name} {self.last_name}"

                @staticmethod
                def calculated_fields():
                    return ["full_name"]
        """
        return []


@dataclass
class Entity(Model):
    """
    Base entity class extending Model with an id field.

    Entities are domain objects that have a unique identity. This class extends
    the Model class to include an 'id' field and inherits all serialization and
    deserialization capabilities.

    The id field can be of any type (str, int, UUID, etc.) depending on your
    application's needs.

    Example:
        @dataclass
        class User(Entity):
            name: str
            email: str

        user = User(id="user-123", name="John", email="john@example.com")
        user_dict = user.asdict()
        # {"id": "user-123", "name": "John", "email": "john@example.com"}
    """

    id: Any
