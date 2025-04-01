from typing import Literal

from nonebot.adapters import Bot
from nonebot.internal.matcher import current_bot
from nonebot.permission import SUPERUSER, Permission
from nonebot_plugin_localstore import get_plugin_data_file
from nonebot_plugin_uninfo import Uninfo
from pydantic import BaseModel, TypeAdapter

DATA_FILE = get_plugin_data_file("trusted.json")
if not DATA_FILE.exists():
    DATA_FILE.write_text("{}")


class TrustData(BaseModel):
    user: set[str] = set()
    group: set[str] = set()


_ta = TypeAdapter(TrustData)
_cache: TrustData | None = None


def load_trust_data(*, use_cache: bool = True) -> TrustData:
    global _cache
    if _cache is None or not use_cache:
        _cache = _ta.validate_json(DATA_FILE.read_text())

    return _cache


def dump_trust_data(data: TrustData) -> None:
    global _cache
    _cache = data

    DATA_FILE.write_text(data.model_dump_json(indent=2))


type TrustedType = Literal["user", "group"]


def set_trusted(
    action: Literal["add", "remove"],
    type: TrustedType,  # noqa: A002
    id: str,
) -> None:
    data = load_trust_data(use_cache=False)
    s = data.user if type == "user" else data.group
    (s.add if action == "add" else s.discard)(f"{current_bot.get().type}:{id}")
    dump_trust_data(data)


def query_trusted(
    adapter: str,
    type: TrustedType,  # noqa: A002
    id: str,
    *,
    use_cache: bool = True,
) -> bool:
    data = load_trust_data(use_cache=use_cache)
    return f"{adapter}:{id}" in (data.user if type == "user" else data.group)


def TrustedUser(*, use_cache: bool = True) -> Permission:  # noqa: N802
    async def _trusted(bot: Bot, info: Uninfo) -> bool:
        return query_trusted(bot.type, "user", info.user.id, use_cache=use_cache) or (
            (scene := info.group or info.channel) is not None
            and query_trusted(bot.type, "group", scene.id, use_cache=use_cache)
        )

    return SUPERUSER | _trusted
