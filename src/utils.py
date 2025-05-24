from collections.abc import Sequence
from pathlib import Path

from msgspec import json as msgjson
from pydantic import BaseModel, TypeAdapter


class ConfigFile[T: BaseModel | Sequence[BaseModel]]:
    _file: Path
    _ta: TypeAdapter[T]
    _default: T

    def __init__(self, file: Path, type_: type[T], default: T) -> None:
        self._file = file
        self._ta = TypeAdapter(type_)
        self._default = default

    def load(self) -> T:
        if not self._file.exists():
            self._file.write_bytes(msgjson.encode(self._ta.dump_python(self._default)))
            return self._ta.validate_python(self._default)

        return self._ta.validate_python(msgjson.decode(self._file.read_bytes()))

    def save(self, data: T) -> None:
        encoded = msgjson.encode(self._ta.dump_python(data))
        self._file.write_bytes(encoded)


class ConfigListFile[T: BaseModel](ConfigFile[list[T]]):
    def __init__(self, file: Path, type_: type[T]) -> None:
        super().__init__(file, list[type_], default=[])

    def add(self, item: T) -> None:
        self.save([*self.load(), item])
