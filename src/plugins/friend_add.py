from datetime import timedelta
from typing import Annotated

from nonebot import get_driver, on_message, on_request, require
from nonebot.adapters.onebot.v11 import Bot, FriendRequestEvent, PrivateMessageEvent
from nonebot.params import EventPlainText
from nonebot.permission import SUPERUSER
from nonebot.rule import Rule

require("nonebot_plugin_alconna")
require("nonebot_plugin_userinfo")
from nonebot_plugin_alconna.uniseg import Reply, Target, UniMessage, UniMsg
from nonebot_plugin_userinfo import EventUserInfo, UserInfo

superusers = get_driver().config.superusers
friend_add = on_request()


@friend_add.handle()
async def _(
    event: FriendRequestEvent,
    info: Annotated[UserInfo, EventUserInfo()],
):
    message = UniMessage.text(f"收到好友申请: {info.user_name}({info.user_id})\n")
    if avatar := info.user_avatar:
        message += UniMessage.image(raw=await avatar.get_image())

    msgid: dict[str, int] = {}
    for target in superusers:
        res = await message.send(Target(target, private=True))
        msgid[target] = res.msg_ids[0]["message_id"]

    def checker(event: PrivateMessageEvent, msg: UniMsg):
        reply_id = int(msg[Reply, 0].id) if msg.has(Reply) else -1
        return reply_id == msgid.get(event.get_user_id(), 0)

    matcher = on_message(
        rule=Rule(checker),
        permission=SUPERUSER,
        temp=True,
        expire_time=timedelta(minutes=10),
    )

    @matcher.handle()
    async def _(bot: Bot, msg: Annotated[str, EventPlainText()]):
        if "接受" in msg:
            await event.approve(bot)
            await matcher.finish("已接受好友申请")
        elif "拒绝" in msg:
            await event.reject(bot)
            await matcher.finish("已拒绝好友申请")
        else:
            await matcher.reject("无效命令")
