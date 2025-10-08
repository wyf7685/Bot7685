from typing import TYPE_CHECKING, Literal

from nonebot.internal.matcher import current_bot
from nonebot.permission import SUPERUSER, Permission
from nonebot_plugin_localstore import get_plugin_data_file
from pydantic import BaseModel

from src.utils import ConfigModelFile

if TYPE_CHECKING:
    from nonebot.adapters import Bot
    from nonebot_plugin_uninfo import Uninfo


@ConfigModelFile.from_model(get_plugin_data_file("trusted.json"))
class TrustData(BaseModel):
    user: set[str] = set()
    group: set[str] = set()


def set_trusted(
    action: Literal["add", "remove"],
    type_: Literal["user", "group"],
    id: str,
) -> None:
    data = TrustData.load(use_cache=False)
    s = data.user if type_ == "user" else data.group
    (s.add if action == "add" else s.discard)(f"{current_bot.get().type}:{id}")
    TrustData.save(data)


def query_trusted(
    adapter: str,
    type_: Literal["user", "group"],
    id: str,
    *,
    use_cache: bool = True,
) -> bool:
    data = TrustData.load(use_cache=use_cache)
    return f"{adapter}:{id}" in (data.user if type_ == "user" else data.group)


def TrustedUser(*, use_cache: bool = True) -> Permission:  # noqa: N802
    async def _trusted(bot: Bot, info: Uninfo) -> bool:
        return query_trusted(bot.type, "user", info.user.id, use_cache=use_cache) or (
            (scene := info.group or info.channel) is not None
            and query_trusted(bot.type, "group", scene.id, use_cache=use_cache)
        )

    return SUPERUSER | _trusted
