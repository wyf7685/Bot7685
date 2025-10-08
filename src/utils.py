import atexit
import contextlib
import functools
import inspect
import shutil
import sys
import tempfile
import threading
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import TYPE_CHECKING, Any, cast

import anyio
import nonebot
from msgspec import json as msgjson
from msgspec import toml as msgtoml
from nonebot.utils import escape_tag
from pydantic import BaseModel, TypeAdapter

if TYPE_CHECKING:
    from nonebot.typing import T_State


def logger_wrapper(logger_name: str, /):  # noqa: ANN201
    logger = nonebot.logger.patch(lambda r: r.update(name="Bot7685"))
    logger_name = escape_tag(logger_name)

    def log(level: str, message: str, exception: Exception | None = None) -> None:
        logger.opt(colors=True, exception=exception).log(
            level, f"<m>{logger_name}</m> | {message}"
        )

    return log


class ConfigFile[T]:
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
        self._cache = cast("T", data) if data is not None else self.load()
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
    ) -> Callable[[type[M]], ConfigModelFile[M]]:
        def decorator(model: type[M]) -> ConfigModelFile[M]:
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


def find_and_link_external() -> None:
    external_dir = Path.cwd() / "external"
    if not external_dir.exists() or not external_dir.is_dir():
        return

    log = logger_wrapper("Bootstrap::Link")

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

        if (egg_info := (repo_root / f"{package_name}.egg-info")).exists():
            egg_link = link_target / egg_info.name
            try:
                egg_link.symlink_to(egg_info.resolve())
            except OSError as exc:
                debug(f"Failed to create symlink for egg-info {egg_info}: {exc}")
            else:
                debug(f"Linked egg-info: {egg_info} -> {egg_link}")
                continue

            try:
                shutil.copytree(egg_info, egg_link)
            except Exception as exc:
                debug(f"Failed to copy egg-info {egg_info}: {exc}")
            else:
                debug(f"Copied egg-info: {egg_info} -> {egg_link}")

    site_idx = next(
        (i for i, p in enumerate(sys.path) if p.endswith("site-packages")),
        len(sys.path),
    )
    sys.path.insert(site_idx, str(link_target))

    @atexit.register
    def _() -> None:
        try:
            shutil.rmtree(link_target)
        except Exception as exc:
            print(f"Failed to remove temporary external link directory: {exc}")  # noqa: T201


def with_semaphore[T: Callable](initial_value: int) -> Callable[[T], T]:
    def decorator(func: T) -> T:
        if inspect.iscoroutinefunction(func):
            sem = anyio.Semaphore(initial_value)

            @functools.wraps(func)
            async def wrapper_async(*args: Any, **kwargs: Any) -> Any:
                async with sem:
                    return await func(*args, **kwargs)

            wrapper = wrapper_async
        else:
            sem = threading.Semaphore(initial_value)

            @functools.wraps(func)
            def wrapper_sync(*args: Any, **kwargs: Any) -> Any:
                with sem:
                    return func(*args, **kwargs)

            wrapper = wrapper_sync

        return cast("T", functools.update_wrapper(wrapper, func))

    return decorator


def ParamOrPrompt(  # noqa: N802
    param: str,
    prompt: str | Callable[[], Awaitable[str]],
) -> Any:
    from nonebot import require
    from nonebot.params import Depends

    require("nonebot_plugin_alconna")
    from nonebot_plugin_alconna import AlconnaMatcher, Arparma, UniMessage

    if not callable(prompt):
        prompt_msg = prompt

        async def fn() -> str:
            resp = await AlconnaMatcher.prompt(prompt_msg)
            if resp is None:
                await AlconnaMatcher.finish("操作已取消")
            return resp.extract_plain_text().strip()

        prompt = fn

    sem_key = "ParamOrPrompt#semaphore"

    async def dependency(arp: Arparma, state: T_State) -> str:
        arg: UniMessage | str | None = arp.all_matched_args.get(param)
        if arg is None:
            if sem_key not in state:
                state[sem_key] = anyio.Semaphore(1)
            async with state[sem_key]:
                arg = await prompt()
        if isinstance(arg, UniMessage):
            arg = arg.extract_plain_text().strip()
        return arg

    return Depends(dependency)


def _setup() -> None:
    with contextlib.suppress(ImportError):
        import humanize

        humanize.activate("zh_CN")


_setup()
