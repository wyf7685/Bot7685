# ruff: noqa: N802

import asyncio
import functools
import inspect
from collections.abc import Awaitable, Callable
from typing import Annotated, cast

from nonebot.adapters import Bot, Event
from nonebot.internal.matcher import current_matcher
from nonebot.params import Depends
from nonebot.permission import SUPERUSER
from nonebot.typing import T_State
from nonebot_plugin_alconna.uniseg import UniMessage
from nonebot_plugin_uninfo import Uninfo

from ..database.kuro_token import KuroToken, KuroTokenDAO
from ..handler import KuroHandler
from ..kuro_api import KuroApi, KuroApiException


def _get_current_state() -> T_State | None:
    try:
        return current_matcher.get().state
    except LookupError:
        return None


def convert_dependent[**P, R](func: Callable[P, Awaitable[R]]) -> type[R]:
    key = f"##state_cache##{func.__name__}##"

    @functools.wraps(func)
    async def wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
        if (state := _get_current_state()) is None:
            return await func(*args, **kwargs)

        if key in state:
            fut: asyncio.Future[R] = state[key]
            result = await fut
        else:
            state[key] = fut = asyncio.Future()
            result = await func(*args, **kwargs)
            fut.set_result(result)

        return result

    r = inspect.signature(func).return_annotation
    return cast(type[R], Annotated[r, Depends(wrapper)])


@convert_dependent
async def IsSuperUser(bot: Bot, event: Event) -> bool:
    return await SUPERUSER(bot, event)


@convert_dependent
async def TokenDAO(session: Uninfo) -> KuroTokenDAO:
    return KuroTokenDAO(session)


@convert_dependent
async def KuroTokenFromKey(ktd: TokenDAO, key: str | None = None) -> KuroToken:
    kuro_token = await ktd.find_token(key)
    if kuro_token is None:
        msg = f"未找到 '{key}' 对应的库洛账号" if key is not None else "未绑定库洛账号"
        await UniMessage.text(msg).finish()

    return kuro_token


@convert_dependent
async def KuroTokenFromKeyRequired(ktd: TokenDAO, key: str) -> KuroToken:
    kuro_token = await ktd.find_token(key)
    if kuro_token is None:
        msg = f"未找到 '{key}' 对应的库洛账号"
        await UniMessage.text(msg).finish()

    return kuro_token


@convert_dependent
async def ApiFromKey(kuro_token: KuroTokenFromKey) -> KuroApi:
    api = KuroApi(kuro_token.token)

    try:
        await api.mine()
    except KuroApiException as err:
        await UniMessage.text(f"token 检查失败: {err.msg}").finish()

    return api


@convert_dependent
async def HandlerFromKey(api: ApiFromKey) -> KuroHandler:
    return KuroHandler(api)


@convert_dependent
async def KuroUserName(api: ApiFromKey) -> str:
    return f"{await api.get_user_name()}({await api.get_user_id()})"
