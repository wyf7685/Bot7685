import atexit
import shutil
import sys
import tempfile
from collections.abc import Callable, Iterable, Sequence
from pathlib import Path
from typing import TYPE_CHECKING, override

import anyio
from msgspec import json as msgjson
from msgspec import toml as msgtoml
from nonebot.internal.driver._lifespan import Lifespan
from nonebot.utils import is_coroutine_callable, logger_wrapper, run_sync
from pydantic import BaseModel, TypeAdapter

if TYPE_CHECKING:
    from nonebot.internal.driver._lifespan import LIFESPAN_FUNC


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

    def remove(self, pred: Callable[[T], bool]) -> None:
        self.save([item for item in self.load() if not pred(item)])


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


class ConcurrentLifespan(Lifespan):
    @staticmethod
    @override
    async def _run_lifespan_func(funcs: Iterable["LIFESPAN_FUNC"]) -> None:
        async with anyio.create_task_group() as tg:
            for func in funcs:
                if not is_coroutine_callable(func):
                    func = run_sync(func)
                tg.start_soon(func)


def find_and_link_external() -> None:
    external_dir = Path.cwd() / "external"
    if not external_dir.exists() or not external_dir.is_dir():
        return

    log = logger_wrapper("Bootstrap:link")

    def debug(msg: str) -> None:
        log("DEBUG", msg)

    link_target = Path(tempfile.mkdtemp(prefix="bot7685_external_"))
    for repo_root in external_dir.iterdir():
        if (
            not repo_root.is_dir()
            or not (toml_file := repo_root / "pyproject.toml").exists()
        ):
            continue

        try:
            project: dict[str, dict[str, str]] = msgtoml.decode(toml_file.read_bytes())
            if (
                not (project_name := project.get("project", {}).get("name", ""))
                or not (package_name := project_name.replace("-", "_"))
                or not (package_path := repo_root / package_name).exists()
                or not package_path.is_dir()
            ):
                continue

        except Exception as exc:
            debug(f"Failed to read project metadata from {repo_root}: {exc}")
            continue

        link_path = link_target / package_name

        try:
            link_path.symlink_to(package_path.resolve())
        except OSError as exc:
            debug(f"Failed to create symlink for {package_name}: {exc}")
        else:
            debug(f"Linked external package: {package_name} -> {link_path}")
            continue

        try:
            shutil.copytree(package_path, link_path)
        except Exception as exc:
            debug(f"Failed to copy external package {package_name}: {exc}")
            continue
        else:
            debug(f"Copied external package: {package_name} -> {link_path}")

    sys.path.insert(1, str(link_target))

    @atexit.register
    def _() -> None:
        try:
            shutil.rmtree(link_target)
        except Exception as exc:
            print(f"Failed to remove temporary external link directory: {exc}")  # noqa: T201
