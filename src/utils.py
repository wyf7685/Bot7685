import contextlib
import datetime as dt
import functools
import inspect
import json
import os
import re
import threading
from collections import deque
from collections.abc import Awaitable, Callable, Mapping
from http import HTTPStatus
from pathlib import Path
from traceback import walk_tb
from types import CoroutineType
from typing import TYPE_CHECKING, Any, Concatenate, Literal, cast, overload
from uuid import uuid4

import anyio
import nonebot
from nonebot.adapters import Event
from nonebot.params import Depends
from nonebot.typing import T_State
from nonebot.utils import escape_tag
from pydantic import BaseModel, TypeAdapter, ValidationError

if TYPE_CHECKING:
    from nonebot_plugin_alconna.uniseg import Receipt, UniMessage

type Supplier[T] = Callable[[], T]
type Decorator[
    **InputP,
    InputR,
    **OutputP = InputP,
    OutputR = InputR,
] = Callable[
    [Callable[InputP, InputR]],
    Callable[OutputP, OutputR],
]
type Coro[R] = CoroutineType[object, object, R]
type AsyncDecorator[
    **InputP,
    InputR,
    **OutputP = InputP,
    OutputR = InputR,
] = Decorator[InputP, Awaitable[InputR], OutputP, Coro[OutputR]]

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
type _LogException = Exception | bool | None


class LoggerWrapper:
    def __init__(self, logger_name: str) -> None:
        self.logger = nonebot.logger.patch(lambda r: r.update(name="Bot7685"))
        self.logger_name = escape_tag(logger_name)

    def log(
        self,
        level: _ValidLogLevel,
        message: str,
        exception: _LogException = None,
    ) -> None:
        self.logger.opt(colors=True, exception=exception).log(
            level, f"<m>{self.logger_name}</m> | {message}"
        )

    __call__ = log

    if TYPE_CHECKING:

        def trace(self, message: str, exception: _LogException = None) -> None: ...
        def debug(self, message: str, exception: _LogException = None) -> None: ...
        def info(self, message: str, exception: _LogException = None) -> None: ...
        def success(self, message: str, exception: _LogException = None) -> None: ...
        def warning(self, message: str, exception: _LogException = None) -> None: ...
        def error(self, message: str, exception: _LogException = None) -> None: ...
        def critical(self, message: str, exception: _LogException = None) -> None: ...
    else:

        def __getattr__(self, item: str) -> Callable[[str, Exception | None], None]:
            level = item.upper()
            if level not in _valid_log_levels:
                raise AttributeError(f"Invalid log level: {item}")

            def method(message: str, exception: _LogException = None) -> None:
                self.log(level, message, exception)

            setattr(self, item, method)
            return method

    def exception(self, message: str) -> None:
        self.log("ERROR", message, exception=True)


def logger_wrapper(logger_name: str, /) -> LoggerWrapper:
    return LoggerWrapper(logger_name)


_ERROR_URL_RE = re.compile(
    r"(?:https?|wss?|file|base64)://[^\s\"'<>]+|data:[^\s\"'<>]+"
)
_ERROR_SECRET_RE = re.compile(
    r"(?i)([\"']?(?:authorization|proxy-authorization|api[_-]?key|"
    r"access[_-]?token|refresh[_-]?token|client[_-]?secret|password|secret|token|"
    r"cookie|set-cookie)[\"']?\s*[:=]\s*)"
    r"(?:\"(?:\\.|[^\"\\])*\"|'(?:\\.|[^'\\])*'|[^\s,;}\]]+)"
)
_ERROR_TOKEN_RE = re.compile(
    r"(?i)\b(?:Bearer|Basic)\s+[^\s\"',;]+|\bsk-[A-Za-z0-9_-]+"
)
_ERROR_PAYLOAD_RE = re.compile(r"\b[A-Za-z0-9+/]{128,}={0,2}")


def _exception_request_secrets(error: BaseException) -> set[str]:
    secrets: set[str] = set()
    request = getattr(error, "request", None)
    headers = getattr(request, "headers", None)
    if isinstance(headers, Mapping):
        for name in (
            "authorization",
            "proxy-authorization",
            "x-api-key",
            "api-key",
            "cookie",
        ):
            value = headers.get(name)
            if isinstance(value, str) and value:
                secrets.add(value)
                if value.lower().startswith("bearer "):
                    secrets.add(value[7:])
    try:
        content = getattr(request, "content", None)
    except RuntimeError:
        content = None
    if isinstance(content, bytes):
        try:
            payload = json.loads(content)
        except ValueError, UnicodeError:
            payload = None
        if isinstance(payload, dict):
            pending = [payload.get(name) for name in ("messages", "input", "prompt")]
            while pending:
                value = pending.pop()
                if isinstance(value, str) and value:
                    secrets.add(value)
                elif isinstance(value, dict):
                    pending.extend(
                        item
                        for name, item in value.items()
                        if name not in {"role", "type"}
                    )
                elif isinstance(value, list):
                    pending.extend(value)
    return secrets


def _exception_text(value: str, secrets: set[str], limit: int = 384) -> str:
    for secret in sorted(secrets, key=len, reverse=True):
        value = value.replace(secret, "[redacted]")
    value = _ERROR_TOKEN_RE.sub("[redacted]", value)
    value = _ERROR_SECRET_RE.sub(r"\1[redacted]", value)
    value = _ERROR_URL_RE.sub("[url]", value)
    value = _ERROR_PAYLOAD_RE.sub("[payload]", value)
    value = " ".join(value.split())
    if len(value) > limit:
        value = value[:limit] + "..."
    return json.dumps(value, ensure_ascii=False)


def format_exception(error: BaseException | None) -> str:
    """Describe failures without dumping request bodies, headers, or frame locals."""

    if error is None:
        return "error=none"
    chain: list[tuple[str, BaseException]] = []
    pending: list[tuple[str, BaseException]] = [("", error)]
    seen: set[int] = set()
    while pending and len(chain) < 6:
        relation, current = pending.pop()
        if id(current) in seen:
            continue
        chain.append((relation, current))
        seen.add(id(current))
        if isinstance(current, BaseExceptionGroup):
            pending.extend(
                ("member", child) for child in reversed(current.exceptions[:3])
            )
        cause = getattr(current, "cause", None)
        if not isinstance(cause, BaseException):
            cause = current.__cause__
        if cause is None and not current.__suppress_context__:
            cause = current.__context__
        if cause is not None:
            pending.append(("caused_by", cause))
    secrets: set[str] = set()
    for _, item in chain:
        secrets.update(_exception_request_secrets(item))
    descriptions: list[str] = []
    for relation, item in chain:
        fields = [f"error={type(item).__name__}"]
        response = getattr(item, "response", None)
        status = getattr(item, "status_code", getattr(response, "status_code", None))
        if isinstance(status, int):
            fields.append(f"status={status}")
        request_id = getattr(item, "request_id", None)
        if request_id is None:
            headers = getattr(response, "headers", None)
            if isinstance(headers, Mapping):
                request_id = headers.get("x-request-id") or headers.get("request-id")
        if isinstance(request_id, str) and request_id:
            fields.append(f"request_id={_exception_text(request_id, secrets, 128)}")
        body = getattr(item, "body", None)
        metadata = body if isinstance(body, Mapping) else {}
        nested = metadata.get("error")
        if isinstance(nested, Mapping):
            metadata = nested
        for name in ("code", "type", "param"):
            value = metadata.get(name, getattr(item, name, None))
            if isinstance(value, str | int):
                fields.append(f"{name}={_exception_text(str(value), secrets, 128)}")
        if isinstance(item, ValidationError):
            problems = item.errors(include_input=False, include_url=False)
            message = "; ".join(
                f"{".".join(str(part) for part in problem["loc"])}: {problem["type"]}"
                for problem in problems[:8]
            )
        elif isinstance(body, Mapping):
            message = metadata.get("message", "")
            if not isinstance(message, str):
                message = ""
        elif isinstance(status, int):
            # SDK messages may stringify the entire response body, including input.
            message = (
                HTTPStatus(status).phrase if status in HTTPStatus else "HTTP error"
            )
            if isinstance(body, str) and not body.lstrip().startswith(("{", "[", "<")):
                message = body
        else:
            message = getattr(item, "detail", None) or str(item)
        if isinstance(message, str) and message:
            fields.append(f"message={_exception_text(message, secrets)}")
        notes = getattr(item, "__notes__", ())
        fields.extend(
            f"context={_exception_text(note, secrets, 256)}" for note in notes[:4]
        )
        if item.__traceback__ is not None:
            sites = deque(walk_tb(item.__traceback__), maxlen=3)
            location = " > ".join(
                f"{Path(frame.f_code.co_filename).name}:{line}:{frame.f_code.co_name}"
                for frame, line in sites
            )
            fields.append(f"at={_exception_text(location, secrets, 256)}")
        if isinstance(item, BaseExceptionGroup):
            fields.append(f"group_errors={len(item.exceptions)}")
        description = " ".join(fields)
        descriptions.append(f"{relation}=[{description}]" if relation else description)
    if pending:
        descriptions.append("error_chain=truncated")
    diagnostic = " ".join(descriptions)
    return (
        diagnostic
        if len(diagnostic) <= 8192
        else diagnostic[:8192] + " diagnostics_truncated=true"
    )


class ConfigFile[T]:
    type_: type[T]
    _file: Path
    _ta: TypeAdapter[T]
    _default: Supplier[T]
    _cache: T | None = None

    def __init__(self, file: Path, type_: type[T], /, default: Supplier[T]) -> None:
        self.type_ = type_
        self._file = file
        self._ta = TypeAdapter(type_)
        self._default = default

    def load(self, *, use_cache: bool = True) -> T:
        if use_cache and self._cache is not None:
            return self._cache

        if self._file.exists():
            self._cache = self._ta.validate_json(self._file.read_bytes())
        else:
            self.save(self._default())
            assert self._cache is not None

        return self._cache

    def save(self, data: T | None = None) -> None:
        value = cast("T", data) if data is not None else self.load()
        encoded = self._ta.dump_json(value)
        self._file.parent.mkdir(parents=True, exist_ok=True)
        temporary = self._file.with_name(f".{self._file.name}.{uuid4().hex}.tmp")
        try:
            with temporary.open("wb") as stream:
                stream.write(encoded)
                stream.flush()
                os.fsync(stream.fileno())
            temporary.replace(self._file)
        finally:
            with contextlib.suppress(FileNotFoundError):
                temporary.unlink()
        self._cache = value


class ConfigModelFile[T: BaseModel](ConfigFile[T]):
    def __init__(
        self,
        file: Path,
        type_: type[T],
        /,
        default: Supplier[T] | None = None,
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
        super().__init__(file, list[type_], default=list)  # ty:ignore[invalid-type-form]

    def add(self, item: T) -> None:
        self.save([*self.load(), item])

    def remove(self, pred: Callable[[T], bool]) -> None:
        self.save([item for item in self.load() if not pred(item)])


def with_semaphore[**P, R](initial_value: int) -> Decorator[P, R]:
    def decorator(func: Callable[P, R]) -> Callable[P, R]:
        if inspect.iscoroutinefunction(func):
            async_sem = anyio.Semaphore(initial_value)

            @functools.wraps(func)
            async def wrapper_async(*args: P.args, **kwargs: P.kwargs) -> R:
                async with async_sem:
                    return await func(*args, **kwargs)

            wrapper = wrapper_async
        else:
            sync_sem = threading.Semaphore(initial_value)

            @functools.wraps(func)
            def wrapper_sync(*args: P.args, **kwargs: P.kwargs) -> R:
                with sync_sem:
                    return func(*args, **kwargs)

            wrapper = wrapper_sync

        return cast("Callable[P, R]", functools.update_wrapper(wrapper, func))

    return decorator


@overload
def copy_signature[F: Callable](source: F, target: Callable[..., object], /) -> F: ...
@overload
def copy_signature[F: Callable](source: F, /) -> Callable[[Callable], F]: ...


def copy_signature[F: Callable](
    source: F,
    target: Callable[..., object] | None = None,
) -> F | Callable[[Callable], F]:
    def decorator(target: Callable[..., object]) -> F:
        return cast("F", functools.update_wrapper(target, source))

    return decorator(target) if target is not None else decorator


def caller_loc_repr(depth: int = 1) -> str:
    if (frame := inspect.currentframe()) is None:
        return "<unknown>"
    for _ in range(depth + 1):
        if frame.f_back is None:
            return "<unknown>"
        frame = frame.f_back
    return f"{frame.f_code.co_filename}:{frame.f_lineno}"


def schedule_recall(receipt: Receipt) -> None:
    if not receipt.recallable:
        return

    loc = caller_loc_repr()

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

        def waiter_handler(event: Event) -> str:
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
    else:
        prompt = cast("Callable[[], Awaitable[str]]", prompt)

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


type AsyncContextSupplier[T] = Supplier[contextlib.AbstractAsyncContextManager[T]]


@overload
def attach_async_context[T, **P, R](
    context: AsyncContextSupplier[T],
    /,
) -> AsyncDecorator[Concatenate[T, P], R, P]: ...
@overload
def attach_async_context[T, **P, R](
    context: AsyncContextSupplier[T],
    /,
    as_param: Literal[False],
) -> AsyncDecorator[P, R]: ...


def attach_async_context[T, **P, R](
    context: AsyncContextSupplier[T],
    /,
    as_param: bool = True,
) -> AsyncDecorator[Concatenate[T, P], R, P] | AsyncDecorator[P, R]:
    if as_param:

        def decorator_with_param(
            func: Callable[Concatenate[T, P], Awaitable[R]],
        ) -> Callable[P, Coro[R]]:

            @functools.wraps(func)
            async def wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
                async with context() as ctx_val:
                    return await func(ctx_val, *args, **kwargs)

            return cast("Callable[P, Coro[R]]", wrapper)

        return decorator_with_param

    def decorator(func: Callable[P, Awaitable[R]]) -> Callable[P, Coro[R]]:
        @functools.wraps(func)
        async def wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
            async with context():
                return await func(*args, **kwargs)

        return cast("Callable[P, Coro[R]]", wrapper)

    return decorator


def humanize_relative_time(delta: dt.timedelta) -> str:
    total_seconds = int(delta.total_seconds())
    is_past = total_seconds < 0
    abs_seconds = abs(total_seconds)

    if abs_seconds < 3600:
        minutes = max(abs_seconds // 60, 1)
        text = f"{minutes} 分钟"
    elif abs_seconds < 86400:
        hours = abs_seconds // 3600
        text = f"{hours} 小时"
    else:
        days = abs_seconds // 86400
        text = f"{days} 天"

    if is_past:
        return f"{text}前"
    return f"{text}后" if abs_seconds < 86400 else f"{text}内"
