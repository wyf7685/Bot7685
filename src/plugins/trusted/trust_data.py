import json
from typing import Literal

from nonebot.compat import model_dump, type_validate_json
from nonebot.internal.matcher import current_bot
from nonebot.permission import SUPERUSER, Permission
from nonebot_plugin_localstore import get_plugin_data_file
from nonebot_plugin_uninfo import Uninfo
from pydantic import BaseModel

DATA_FILE = get_plugin_data_file("trusted.json")
if not DATA_FILE.exists():
    DATA_FILE.write_text("{}")


class TrustData(BaseModel):
    user: set[str] = set()
    group: set[str] = set()


def load_trust_data() -> TrustData:
    return type_validate_json(TrustData, DATA_FILE.read_text())


def dump_trust_data(data: TrustData) -> None:
    DATA_FILE.write_text(json.dumps(model_dump(data), ensure_ascii=False, indent=2))


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
        (group := info.group or info.channel) is not None
        and query_trusted("group", group.id)
    )


TrustedUser = SUPERUSER | _trusted
