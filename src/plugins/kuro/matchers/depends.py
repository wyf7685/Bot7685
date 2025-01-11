# ruff: noqa: N802

import functools
import inspect
from collections.abc import Awaitable, Callable
from typing import Annotated, cast

from nonebot.adapters import Bot, Event
from nonebot.internal.matcher import current_matcher
from nonebot.params import Depends
from nonebot.permission import SUPERUSER
from nonebot_plugin_alconna.uniseg import UniMessage
from nonebot_plugin_uninfo import Uninfo

from ..database.kuro_token import KuroTokenDAO
from ..kuro_api import KuroApi, KuroApiException

type AsyncCallable[**P, R] = Callable[P, Awaitable[R]]


def state_cache[**P, R](func: AsyncCallable[P, R]) -> AsyncCallable[P, R]:
    key = f"##state_cache##{func.__name__}##"

    @functools.wraps(func)
    async def wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
        try:
            state = current_matcher.get().state
        except LookupError:
            state = {}

        if key not in state:
            state[key] = await func(*args, **kwargs)
        return state[key]

    return wrapper


def convert_dependent[R](func: AsyncCallable[..., R]) -> type[R]:
    r = inspect.signature(func).return_annotation
    return cast(type[R], Annotated[r, Depends(func)])


@convert_dependent
@state_cache
async def IsSuperUser(bot: Bot, event: Event) -> bool:
    return await SUPERUSER(bot, event)


@convert_dependent
@state_cache
async def ApiFromKey(session: Uninfo, key: str) -> KuroApi:
    kuro_token = await KuroTokenDAO(session).find_token(key)
    if kuro_token is None:
        await UniMessage.text("未找到对应的库洛 ID").finish()

    api = KuroApi(kuro_token.token)

    try:
        await api.mine()
    except KuroApiException as err:
        await UniMessage.text(f"token 检查失败: {err.msg}").finish()

    return api


@convert_dependent
@state_cache
async def KuroUserName(api: ApiFromKey) -> str:
    return f"{await api.get_user_name()}({await api.get_user_id()})"
