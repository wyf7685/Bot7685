import contextlib
import functools
import inspect
import threading
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any, cast

import anyio
import nonebot
from msgspec import json as msgjson
from nonebot.params import Depends
from nonebot.typing import T_State
from nonebot.utils import escape_tag
from pydantic import BaseModel, TypeAdapter


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


def with_semaphore[T: Callable](initial_value: int) -> Callable[[T], T]:
    def decorator(func: T) -> T:
        if inspect.iscoroutinefunction(func):
            async_sem = anyio.Semaphore(initial_value)

            @functools.wraps(func)
            async def wrapper_async(*args: Any, **kwargs: Any) -> Any:
                async with async_sem:
                    return await func(*args, **kwargs)

            wrapper = wrapper_async
        else:
            sync_sem = threading.Semaphore(initial_value)

            @functools.wraps(func)
            def wrapper_sync(*args: Any, **kwargs: Any) -> Any:
                with sync_sem:
                    return func(*args, **kwargs)

            wrapper = wrapper_sync

        return cast("T", functools.update_wrapper(wrapper, func))

    return decorator


def ParamOrPrompt(  # noqa: N802
    param: str,
    prompt: str | Callable[[], Awaitable[str]],
) -> Any:
    from nonebot import require

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


def ignore_exc[**P](
    func: Callable[P, Awaitable[object]],
) -> Callable[P, Awaitable[None]]:
    @functools.wraps(func)
    async def wrapper(*args: P.args, **kwargs: P.kwargs) -> None:
        with contextlib.suppress(Exception):
            await func(*args, **kwargs)

    return wrapper


def _setup() -> None:
    with contextlib.suppress(ImportError):
        import humanize

        humanize.activate("zh_CN")


_setup()
