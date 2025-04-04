import contextlib

import anyio
from nonebot import get_driver, on_message, on_type, require
from nonebot.adapters.onebot.v11 import Bot, FriendRequestEvent, PrivateMessageEvent
from nonebot.permission import SUPERUSER
from nonebot.plugin import PluginMetadata

require("nonebot_plugin_alconna")
require("nonebot_plugin_uninfo")
from nonebot_plugin_alconna.uniseg import Receipt, Reply, Target, UniMessage, UniMsg
from nonebot_plugin_uninfo import Uninfo

__plugin_meta__ = PluginMetadata(
    name="friend_add",
    description="好友申请处理",
    usage="自动处理好友申请",
    type="application",
    supported_adapters={"~onebot.v11"},
)


@on_type(FriendRequestEvent).handle()
async def handle(event: FriendRequestEvent, info: Uninfo) -> None:
    name = info.user.nick or info.user.name or info.user.id
    message = UniMessage.text(f"收到好友申请: {name}({info.user.id})\n")
    if avatar := info.user.avatar:
        message.image(url=avatar)
    message.text("\n回复 “接受” 或 “拒绝”")

    receipts: dict[str, Receipt] = {}
    for user_id in get_driver().config.superusers:
        adapter, _, user = user_id.partition(":")
        if adapter and adapter != "onebot":
            continue

        target = Target.user(user)
        with contextlib.suppress(Exception):
            receipts[user_id] = await message.send(target)

    if not receipts:
        return

    async def rule(event: PrivateMessageEvent, msg: UniMsg) -> bool:
        return (
            (receipt := receipts.get(event.get_user_id())) is not None
            and (reply := receipt.get_reply()) is not None
            and len(reply) > 0
            and (r := reply[0])
            and msg.has(Reply)
            and msg[Reply, 0].id == r.id
            and msg.extract_plain_text() in {"接受", "拒绝"}
        )

    async def handler(bot: Bot, msg: UniMsg) -> None:
        await (
            event.approve
            if (text := msg.extract_plain_text()) == "接受"
            else event.reject
        )(bot)
        await UniMessage.text(f"已{text}该好友申请").send()
        finished.set()

    matcher = on_message(
        rule=rule,
        permission=SUPERUSER,
        handlers=[handler],
        temp=True,
    )
    finished = anyio.Event()
    with anyio.move_on_after(10 * 60):
        await finished.wait()

    if not finished.is_set():
        matcher.destroy()
        for receipt in receipts.values():
            await receipt.reply("操作超时，将忽略该好友申请")
