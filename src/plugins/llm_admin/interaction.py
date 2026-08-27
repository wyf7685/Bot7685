from __future__ import annotations

import asyncio
from collections.abc import Callable, Sequence
from contextlib import asynccontextmanager
from typing import cast

import nonebot_plugin_waiter.unimsg as waiter
from nonebot_plugin_alconna import UniMessage

_CANCEL_WORDS = {"取消", "cancel", "quit", "exit"}
_SESSION_GUARD = asyncio.Lock()
_SESSION_ACTIVE = False


class InteractionCancelled(Exception):
    pass


class InteractionTimeout(Exception):
    pass


class InteractionLimited(Exception):
    pass


class InteractionBusy(Exception):
    pass


@asynccontextmanager
async def configuration_session():
    global _SESSION_ACTIVE
    async with _SESSION_GUARD:
        if _SESSION_ACTIVE:
            raise InteractionBusy
        _SESSION_ACTIVE = True
    try:
        yield
    finally:
        async with _SESSION_GUARD:
            _SESSION_ACTIVE = False


async def ask_value[T](
    prompt: str,
    parser: Callable[[str], T],
    *,
    default: T | None = None,
    allow_empty_default: bool = False,
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
        if text.casefold() in _CANCEL_WORDS:
            raise InteractionCancelled
        if not text and allow_empty_default:
            return cast("T", default)
        try:
            return parser(text)
        except ValueError:
            await UniMessage.text(error_message).send()
    raise InteractionLimited


async def ask_text(
    prompt: str,
    *,
    default: str | None = None,
    allow_empty_default: bool = False,
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
        allow_empty_default=allow_empty_default,
        error_message="输入不能为空。",
    )


async def ask_int(
    prompt: str,
    *,
    minimum: int,
    default: int | None = None,
    allow_empty_default: bool = False,
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
        allow_empty_default=allow_empty_default,
        error_message=f"请输入不小于 {minimum} 的整数。",
    )


async def ask_float(
    prompt: str,
    *,
    minimum_exclusive: float,
    default: float | None = None,
    allow_empty_default: bool = False,
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
        allow_empty_default=allow_empty_default,
        error_message=f"请输入大于 {minimum_exclusive:g} 的数字。",
    )


async def ask_bool(
    prompt: str,
    *,
    default: bool | None = None,
    allow_empty_default: bool = False,
) -> bool:
    truthy = {"是", "y", "yes", "true", "1", "on"}
    falsy = {"否", "n", "no", "false", "0", "off"}

    def parse(value: str) -> bool:
        normalized = value.casefold()
        if normalized in truthy:
            return True
        if normalized in falsy:
            return False
        raise ValueError

    return await ask_value(
        f"{prompt} [是/否]",
        parse,
        default=default,
        allow_empty_default=allow_empty_default,
        error_message="请回复“是”或“否”。",
    )


async def ask_choice[T](
    prompt: str,
    choices: Sequence[tuple[str, T]],
    *,
    default: T | None = None,
    allow_empty_default: bool = False,
) -> T:
    if not choices:
        raise ValueError("choices must not be empty")
    lines = [prompt]
    lines.extend(f"{index}. {label}" for index, (label, _) in enumerate(choices, 1))
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
        allow_empty_default=allow_empty_default,
        error_message="请输入候选项编号或名称。",
    )


async def confirm(prompt: str) -> bool:
    return await ask_bool(prompt)


__all__ = [
    "InteractionBusy",
    "InteractionCancelled",
    "InteractionLimited",
    "InteractionTimeout",
    "ask_bool",
    "ask_choice",
    "ask_float",
    "ask_int",
    "ask_text",
    "configuration_session",
    "confirm",
]
