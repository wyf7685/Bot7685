import json
from dataclasses import asdict
from datetime import datetime, timedelta
from typing import Self, cast, override


class DatetimeJsonEncoder(json.JSONEncoder):
    @override
    def default(self, o: object) -> object:
        if isinstance(o, datetime):
            return int(o.timestamp())
        if isinstance(o, timedelta):
            return o.total_seconds()
        return cast(object, json.JSONEncoder.default(self, o))


class ModelMixin:
    @classmethod
    def load(cls, data: dict[str, object]) -> Self:
        return cls(**data)

    def dump(self) -> dict[str, object]:
        return cast(dict[str, object], json.loads(self.dump_json()))

    def dump_json(self) -> str:
        return json.dumps(asdict(self), ensure_ascii=False, cls=DatetimeJsonEncoder)  # pyright:ignore[reportArgumentType]
