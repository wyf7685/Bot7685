import contextlib
import functools
import inspect
import threading
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import TYPE_CHECKING, Any, Literal, cast

import anyio
import nonebot
from msgspec import json as msgjson
from nonebot.adapters import Event
from nonebot.params import Depends
from nonebot.typing import T_State
from nonebot.utils import escape_tag
from pydantic import BaseModel, TypeAdapter

if TYPE_CHECKING:
    from nonebot_plugin_alconna.uniseg import Receipt, UniMessage


type _ValidLogLevel = Literal[
    "TRACE", "DEBUG", "INFO", "SUCCESS", "WARNING", "ERROR", "CRITICAL"
]
_valid_log_levels: set[_ValidLogLevel] = {
    "TRACE",
    "DEBUG",
    "INFO",
    "SUCCESS",
    "WARNING",
    "ERROR",
    "CRITICAL",
}


class LoggerWrapper:
    def __init__(self, logger_name: str) -> None:
        self.logger = nonebot.logger.patch(lambda r: r.update(name="Bot7685"))
        self.logger_name = escape_tag(logger_name)

    def log(
        self, level: _ValidLogLevel, message: str, exception: Exception | None = None
    ) -> None:
        self.logger.opt(colors=True, exception=exception).log(
            level, f"<m>{self.logger_name}</m> | {message}"
        )

    __call__ = log

    if TYPE_CHECKING:

        def trace(self, message: str, exception: Exception | None = None) -> None: ...
        def debug(self, message: str, exception: Exception | None = None) -> None: ...
        def info(self, message: str, exception: Exception | None = None) -> None: ...
        def success(self, message: str, exception: Exception | None = None) -> None: ...
        def warning(self, message: str, exception: Exception | None = None) -> None: ...
        def error(self, message: str, exception: Exception | None = None) -> None: ...
        def critical(
            self, message: str, exception: Exception | None = None
        ) -> None: ...
    else:

        def __getattr__(self, item: str) -> Callable[[str, Exception | None], None]:
            level = item.upper()
            if level not in _valid_log_levels:
                raise AttributeError(f"Invalid log level: {item}")

            def method(message: str, exception: Exception | None = None) -> None:
                self.log(level, message, exception)

            setattr(self, item, method)
            return method


def logger_wrapper(logger_name: str, /) -> LoggerWrapper:
    return LoggerWrapper(logger_name)


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


def schedule_recall(receipt: Receipt) -> None:
    if not receipt.recallable:
        return

    if (frame := inspect.currentframe()) and frame.f_back:
        frame = frame.f_back
        loc = f"{frame.f_code.co_filename}:{frame.f_lineno}"
    else:
        loc = "<unknown>"
    del frame

    async def safe_recall() -> None:
        try:
            await receipt.recall()
        except Exception as exc:
            nonebot.logger.opt(colors=True).warning(
                f"Failed to recall message (at <c>{escape_tag(loc)}</>):"
                f" <r>{escape_tag(repr(exc))}</>"
            )

    nonebot.get_driver().task_group.start_soon(safe_recall)


def ParamOrPrompt(  # noqa: N802
    param: str,
    prompt: str | UniMessage | Callable[[], Awaitable[str]],
    timeout: float = 120,
    block: bool = True,
) -> Any:
    nonebot.require("nonebot_plugin_alconna")
    from nonebot_plugin_alconna import Arparma, UniMessage

    if not callable(prompt):
        nonebot.require("nonebot_plugin_waiter")
        prompt_msg = UniMessage.text(prompt) if isinstance(prompt, str) else prompt

        async def waiter_handler(event: Event) -> str:
            return event.get_message().extract_plain_text().strip()

        async def prompt_fn() -> str:
            from nonebot_plugin_waiter import waiter

            receipt = await prompt_msg.send()
            wait = waiter(["message"], keep_session=True, block=block)(waiter_handler)
            resp = await wait.wait(timeout=timeout)
            schedule_recall(receipt)

            if resp is None:
                await UniMessage.text("操作已取消").finish()
            return resp

        prompt = prompt_fn

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
