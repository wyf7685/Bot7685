from collections.abc import Callable, Sequence
from pathlib import Path

from msgspec import json as msgjson
from pydantic import BaseModel, TypeAdapter


class ConfigFile[T: BaseModel | Sequence[BaseModel]]:
    type_: type[T]
    _file: Path
    _ta: TypeAdapter[T]
    _default: Callable[[], T]
    _cache: T | None = None

    def __init__(self, file: Path, type_: type[T], /, default: Callable[[], T]) -> None:
        self.type_ = type_
        self._file = file
        self._ta = TypeAdapter(type_)
        self._default = default

    def load(self, *, use_cache: bool = True) -> T:
        if use_cache and self._cache is not None:
            return self._cache

        if self._file.exists():
            obj = msgjson.decode(self._file.read_bytes())
            self._cache = self._ta.validate_python(obj)
        else:
            self.save(self._default())
            assert self._cache is not None

        return self._cache

    def save(self, data: T | None = None) -> None:
        self._cache = data if data is not None else self.load()
        encoded = msgjson.encode(self._ta.dump_python(self._cache))
        self._file.write_bytes(encoded)


class ConfigModelFile[T: BaseModel](ConfigFile[T]):
    def __init__(
        self,
        file: Path,
        type_: type[T],
        /,
        default: Callable[[], T] | None = None,
    ) -> None:
        super().__init__(file, type_, default=default or type_)

    @staticmethod
    def from_model[M: BaseModel](
        file: Path, /
    ) -> Callable[[type[M]], "ConfigModelFile[M]"]:
        def decorator(model: type[M]) -> "ConfigModelFile[M]":
            return ConfigModelFile[M](file, model)

        return decorator


class ConfigListFile[T: BaseModel](ConfigFile[list[T]]):
    def __init__(self, file: Path, type_: type[T], /) -> None:
        super().__init__(file, list[type_], default=list)

    def add(self, item: T) -> None:
        self.save([*self.load(), item])


async def orm_upgrade() -> None:
    from argparse import Namespace

    from nonebot_plugin_orm import _init_orm, migrate
    from nonebot_plugin_orm.utils import StreamToLogger
    from sqlalchemy.util import greenlet_spawn

    _init_orm()

    cmd_opts = Namespace()
    with migrate.AlembicConfig(stdout=StreamToLogger(), cmd_opts=cmd_opts) as config:
        cmd_opts.cmd = (migrate.upgrade, [], [])
        await greenlet_spawn(migrate.upgrade, config)
