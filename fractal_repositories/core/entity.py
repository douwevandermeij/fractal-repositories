from dataclasses import dataclass, fields
from datetime import date, datetime, time
from decimal import Decimal
from typing import Any, Dict


@dataclass
class Model:
    @classmethod
    def clean(cls, **kwargs):
        field_names = {
            f.name
            for f in fields(cls)
            if f.type not in (date, datetime) or kwargs.get(f.name)
        }
        return cls(**{k: v for k, v in kwargs.items() if k in field_names})  # NOQA

    @classmethod
    def from_dict(cls, data):
        return cls.clean(**data)

    def update(self, model: Dict):
        current = self.asdict()
        current.update(model)
        return self.from_dict(current)

    def asdict(self, *, skip_types=None, use_timezone_z=False):
        if skip_types is None:
            skip_types = []
        field_names = set(
            f.name for f in fields(self) if f.name not in self.calculated_fields()
        )

        def _asdict(v):
            if issubclass(type(v), (Model, Entity)):
                return v.asdict(skip_types=skip_types, use_timezone_z=use_timezone_z)
            elif isinstance(v, list) and list not in skip_types:
                return [_asdict(i) for i in v]
            elif isinstance(v, Decimal) and Decimal not in skip_types:
                return f"{v:.2f}"
            elif type(v) is date and date not in skip_types:
                return datetime.combine(v, time.min).strftime("%Y-%m-%d")
            elif type(v) is datetime and datetime not in skip_types:
                return (
                    v.isoformat().replace("+00:00", "Z")
                    if use_timezone_z
                    else v.isoformat()
                )
            return v

        ret = {k: _asdict(v) for k, v in self.__dict__.items() if k in field_names}
        return ret

    @staticmethod
    def calculated_fields():
        return []


@dataclass
class Entity(Model):
    id: Any
