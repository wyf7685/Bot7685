from typing import Literal

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


def load_trust_data() -> TrustData:
    return _ta.validate_json(DATA_FILE.read_text())


def dump_trust_data(data: TrustData) -> None:
    DATA_FILE.write_text(data.model_dump_json(indent=2))


def set_trusted(
    action: Literal["add", "remove"],
    type: Literal["user", "group"],  # noqa: A002
    id: str,
) -> None:
    data = load_trust_data()
    s = data.user if type == "user" else data.group
    (s.add if action == "add" else s.discard)(f"{current_bot.get().type}:{id}")
    dump_trust_data(data)


def query_trusted(
    type: Literal["user", "group"],  # noqa: A002
    id: str,
) -> bool:
    try:
        bot = current_bot.get()
    except LookupError:
        return False

    data = load_trust_data()
    return f"{bot.type}:{id}" in (data.user if type == "user" else data.group)


@Permission
async def _trusted(info: Uninfo) -> bool:
    return query_trusted("user", info.user.id) or (
        (scene := info.group or info.channel) is not None
        and query_trusted("group", scene.id)
    )


TrustedUser = SUPERUSER | _trusted
