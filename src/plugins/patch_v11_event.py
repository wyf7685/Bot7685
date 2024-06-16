from typing import override

from nonebot import get_driver
from nonebot.adapters.onebot.utils import highlight_rich_message
from nonebot.adapters.onebot.v11 import Bot
from nonebot.adapters.onebot.v11.event import GroupMessageEvent, PrivateMessageEvent
from nonebot.log import logger
from nonebot.utils import escape_tag
from pydantic import BaseModel


class GroupInfo(BaseModel):
    group_id: int
    group_name: str
    member_count: int
    max_member_count: int


group_info_cache: dict[int, GroupInfo] = {}


async def update_group_cache(bot: Bot):
    for info in await bot.get_group_list():
        info = GroupInfo.model_validate(info)
        group_info_cache[info.group_id] = info


def patch_private():
    @override
    def get_event_description(self: PrivateMessageEvent) -> str:
        sender = escape_tag(
            f"{name}({self.user_id})"
            if (name := (self.sender.card or self.sender.nickname))
            else str(self.user_id)
        )
        return (
            f"Message {self.message_id} from <le>{sender}</le> "
            f"{''.join(highlight_rich_message(repr(self.original_message.to_rich_text())))}"
        )

    PrivateMessageEvent.get_event_description = get_event_description
    logger.success("Patched PrivateMessageEvent.get_event_description")


def patch_group():
    @override
    def get_event_description(self: GroupMessageEvent) -> str:
        sender = escape_tag(
            f"{name}({self.user_id})"
            if (name := (self.sender.card or self.sender.nickname))
            else str(self.user_id)
        )
        return (
            f"Message {self.message_id} from <le>{sender}</le>@[群:{self.group_id}] "
            f"{''.join(highlight_rich_message(repr(self.original_message.to_rich_text())))}"
        )

    GroupMessageEvent.get_event_description = get_event_description
    logger.success("Patched GroupMessageEvent.get_event_description")


@get_driver().on_startup
def on_startup():
    patch_private()
    patch_group()


@get_driver().on_bot_connect
async def on_bot_connect(bot: Bot):
    await update_group_cache(bot)
