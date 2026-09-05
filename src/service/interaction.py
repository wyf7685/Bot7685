import asyncio
from collections.abc import AsyncIterator, Callable, Sequence
from contextlib import asynccontextmanager
from enum import Enum, auto
from typing import Final, Literal, overload

import nonebot_plugin_waiter.unimsg as waiter
from nonebot.plugin import PluginMetadata
from nonebot_plugin_alconna import UniMessage
from pydantic import SecretStr

__plugin_meta__ = PluginMetadata(
    name="Interaction",
    description="Typed conversational input and fail-fast session guards",
    usage="ask_value / ask_text / ask_secret / SessionGuard",
    type="library",
)

_CANCEL_WORDS = {"取消", "cancel", "quit", "exit"}
_DEFAULT_WORDS = {"默认", "default", "保留", "keep"}
_SECRET_EMPTY_WORDS = {"空", "none", "null", "-"}
_TRUTHY_WORDS = {"是", "y", "yes", "true", "1", "on"}
_FALSY_WORDS = {"否", "n", "no", "false", "0", "off"}


class Missing(Enum):
    """Distinguish an omitted default from an explicit None default."""

    VALUE = auto()


MISSING: Final = Missing.VALUE


class InteractionCancelled(Exception):
    pass


class InteractionTimeout(Exception):
    pass


class InteractionLimited(Exception):
    pass


class InteractionBusy(Exception):
    pass


class SessionGuard:
    """Reject overlapping operations within this guard's scope."""

    def __init__(self) -> None:
        self._lock = asyncio.Lock()

    @asynccontextmanager
    async def acquire(self) -> AsyncIterator[None]:
        # An uncontended asyncio lock acquires without suspending this task.
        if self._lock.locked():
            raise InteractionBusy
        async with self._lock:
            yield


async def ask_value[T](
    prompt: str,
    parser: Callable[[str], T],
    *,
    default: T | Missing = MISSING,
    retries: int = 3,
    timeout_seconds: float = 60,
    error_message: str = "输入无效，请重新输入。",
) -> T:
    for _ in range(retries):
        result = await waiter.prompt(
            f"{prompt}\n回复“取消”可结束配置。",
            timeout=timeout_seconds,
        )
        if result is None:
            raise InteractionTimeout
        text = result.extract_plain_text().strip()
        normalized = text.casefold()
        if normalized in _CANCEL_WORDS:
            raise InteractionCancelled
        if normalized in _DEFAULT_WORDS and not isinstance(default, Missing):
            return default
        try:
            return parser(text)
        except ValueError:
            await UniMessage.text(error_message).send()
    raise InteractionLimited


async def ask_text(
    prompt: str,
    *,
    default: str | Missing = MISSING,
) -> str:
    def parse(value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError
        return value

    return await ask_value(
        prompt,
        parse,
        default=default,
        error_message="输入不能为空。",
    )


async def ask_int(
    prompt: str,
    *,
    minimum: int,
    default: int | Missing = MISSING,
) -> int:
    def parse(value: str) -> int:
        parsed = int(value)
        if parsed < minimum:
            raise ValueError
        return parsed

    return await ask_value(
        prompt,
        parse,
        default=default,
        error_message=f"请输入不小于 {minimum} 的整数。",
    )


async def ask_float(
    prompt: str,
    *,
    minimum_exclusive: float,
    default: float | Missing = MISSING,
) -> float:
    def parse(value: str) -> float:
        parsed = float(value)
        if parsed <= minimum_exclusive:
            raise ValueError
        return parsed

    return await ask_value(
        prompt,
        parse,
        default=default,
        error_message=f"请输入大于 {minimum_exclusive:g} 的数字。",
    )


async def ask_bool(
    prompt: str,
    *,
    default: bool | Missing = MISSING,
) -> bool:
    def parse(value: str) -> bool:
        normalized = value.casefold()
        if normalized in _TRUTHY_WORDS:
            return True
        if normalized in _FALSY_WORDS:
            return False
        raise ValueError

    default_hint = (
        f"，回复“默认”选择{"是" if default else "否"}" if default is not MISSING else ""
    )
    return await ask_value(
        f"{prompt} [是/否{default_hint}]",
        parse,
        default=default,
        error_message="请回复“是”或“否”。",
    )


async def ask_choice[T](
    prompt: str,
    choices: Sequence[tuple[str, T]],
    *,
    default: T | Missing = MISSING,
) -> T:
    if not choices:
        raise ValueError("choices must not be empty")
    lines = [prompt]
    lines.extend(
        f"{index}. {label}"
        + (
            "（默认；回复“默认”选择）"
            if default is not MISSING and value == default
            else ""
        )
        for index, (label, value) in enumerate(choices, 1)
    )
    by_label = {label.casefold(): value for label, value in choices}

    def parse(text: str) -> T:
        if text.isdigit() and 1 <= (index := int(text)) <= len(choices):
            return choices[index - 1][1]
        try:
            return by_label[text.casefold()]
        except KeyError as error:
            raise ValueError from error

    return await ask_value(
        "\n".join(lines),
        parse,
        default=default,
        error_message="请输入候选项编号或名称。",
    )


@overload
async def ask_secret(
    prompt: str,
    *,
    default: SecretStr | Missing = MISSING,
    optional: Literal[False] = False,
) -> SecretStr: ...


@overload
async def ask_secret(
    prompt: str,
    *,
    default: SecretStr | Missing | None = MISSING,
    optional: Literal[True],
) -> SecretStr | None: ...


async def ask_secret(
    prompt: str,
    *,
    default: SecretStr | Missing | None = MISSING,
    optional: bool = False,
) -> SecretStr | None:
    if not optional and default is None:
        raise ValueError("A required secret cannot have a None default")

    def parse(value: str) -> SecretStr | None:
        value = value.strip()
        if optional and value.casefold() in _SECRET_EMPTY_WORDS:
            return None
        if not value:
            raise ValueError
        return SecretStr(value)

    default_hint = "；回复“默认”保留当前值" if default is not MISSING else ""
    empty_hint = "；回复“空”清空" if optional else ""
    return await ask_value(
        f"{prompt}{default_hint}{empty_hint}",
        parse,
        default=default,
        error_message="输入不能为空。",
    )


async def confirm(prompt: str) -> bool:
    return await ask_bool(prompt)


__all__ = [
    "MISSING",
    "InteractionBusy",
    "InteractionCancelled",
    "InteractionLimited",
    "InteractionTimeout",
    "Missing",
    "SessionGuard",
    "ask_bool",
    "ask_choice",
    "ask_float",
    "ask_int",
    "ask_secret",
    "ask_text",
    "ask_value",
    "confirm",
]
