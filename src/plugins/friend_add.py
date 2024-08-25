import asyncio
import contextlib
from typing import Annotated

from nonebot import get_driver, on_message, on_type, require
from nonebot.adapters.onebot.v11 import Bot, FriendRequestEvent, PrivateMessageEvent
from nonebot.permission import SUPERUSER

require("nonebot_plugin_alconna")
require("nonebot_plugin_userinfo")
from nonebot_plugin_alconna.uniseg import Reply, Target, UniMessage, UniMsg, Receipt
from nonebot_plugin_userinfo import EventUserInfo, UserInfo


@on_type(FriendRequestEvent).handle()
async def _(event: FriendRequestEvent, info: Annotated[UserInfo, EventUserInfo()]):
    message = UniMessage.text(f"收到好友申请: {info.user_name}({info.user_id})\n")
    if avatar := info.user_avatar:
        message.image(raw=await avatar.get_image())
    message.text("\n回复 “接受” 或 “拒绝”")

    receipts: dict[str, Receipt] = {}
    for user_id in get_driver().config.superusers:
        with contextlib.suppress(Exception):
            receipts[user_id] = await message.send(Target(user_id, private=True))

    if not receipts:
        return

    async def rule(event: PrivateMessageEvent, msg: UniMsg):
        return (
            (receipt := receipts.get(event.get_user_id())) is not None
            and (reply := receipt.get_reply()) is not None
            and msg.has(Reply)
            and msg[Reply, 0].id == reply.id
            and msg.extract_plain_text() in {"接受", "拒绝"}
        )

    matcher = on_message(rule=rule, permission=SUPERUSER, temp=True)
    task = asyncio.create_task(asyncio.sleep(10 * 60))

    @matcher.handle()
    async def _(bot: Bot, msg: UniMsg):
        await (
            event.approve
            if (text := msg.extract_plain_text()) == "接受"
            else event.reject
        )(bot)
        await UniMessage.text(f"已{text}该好友申请").send()
        task.cancel()

    with contextlib.suppress(Exception):
        await task
        matcher.destroy()
        for receipt in receipts.values():
            await receipt.reply("操作超时，将忽略该好友申请")
