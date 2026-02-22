import contextlib

from nonebot import get_driver, on_type, require
from nonebot.adapters.milky import Bot as MilkyBot
from nonebot.adapters.milky import event as milky_event
from nonebot.adapters.onebot.v11 import Bot as OB11Bot
from nonebot.adapters.onebot.v11 import event as ob11_event
from nonebot.permission import SUPERUSER
from nonebot.plugin import PluginMetadata

require("nonebot_plugin_alconna")
require("nonebot_plugin_uninfo")
require("nonebot_plugin_waiter")
import nonebot_plugin_waiter as waiter
from nonebot_plugin_alconna.uniseg import Receipt, Reply, Target, UniMessage, UniMsg
from nonebot_plugin_uninfo import Uninfo

__plugin_meta__ = PluginMetadata(
    name="friend_add",
    description="好友申请处理",
    usage="自动处理好友申请",
    type="application",
    supported_adapters={"~onebot.v11", "~milky"},
)


@on_type(ob11_event.FriendRequestEvent).handle()
async def handle(
    bot: OB11Bot,
    event: ob11_event.FriendRequestEvent,
    info: Uninfo,
) -> None:
    name = info.user.nick or info.user.name or info.user.id
    message = UniMessage.text(f"收到好友申请: {name}({info.user.id})\n")
    if avatar := info.user.avatar:
        message.image(url=avatar)
    message.text("\n回复 “接受” 或 “拒绝”")

    receipts: dict[str, Receipt] = {}
    for user_id in get_driver().config.superusers:
        adapter, _, user = user_id.partition(":")
        if adapter and adapter.lower() != bot.adapter.get_name().lower():
            continue

        with contextlib.suppress(Exception):
            receipts[user_id] = await Target.user(user).send(message)

    if not receipts:
        return

    async def rule(event: ob11_event.PrivateMessageEvent, msg: UniMsg) -> bool:
        return (
            (receipt := receipts.get(event.get_user_id())) is not None
            and (reply := receipt.get_reply()) is not None
            and len(reply) > 0
            and msg.has(Reply)
            and msg[Reply, 0].id == reply[0].id
            and msg.extract_plain_text() in {"接受", "拒绝"}
        )

    @waiter.waiter(
        [ob11_event.PrivateMessageEvent],
        keep_session=False,
        rule=rule,
        permission=SUPERUSER,
    )
    def wait(event: ob11_event.PrivateMessageEvent) -> bool:
        return event.get_message().extract_plain_text() == "接受"

    if (res := await wait.wait(timeout=10 * 60)) is not None:
        await (event.approve if res else event.reject)(bot)
    else:
        for receipt in receipts.values():
            await receipt.reply("操作超时，将忽略该好友申请")


@on_type(milky_event.FriendRequestEvent).handle()
async def handle_milky(
    bot: MilkyBot,
    event: milky_event.FriendRequestEvent,
    info: Uninfo,
) -> None:
    name = info.user.nick or info.user.name or info.user.id
    message = UniMessage.text(f"收到好友申请: {name}({info.user.id})\n")
    if avatar := info.user.avatar:
        message.image(url=avatar)
    message.text("\n回复 “接受” 或 “拒绝”")

    receipts: dict[str, Receipt] = {}
    for user_id in get_driver().config.superusers:
        adapter, _, user = user_id.partition(":")
        if adapter and adapter.lower() != bot.adapter.get_name().lower():
            continue

        with contextlib.suppress(Exception):
            receipts[user_id] = await Target.user(user).send(message)

    if not receipts:
        return

    async def rule(event: milky_event.FriendMessageEvent, msg: UniMsg) -> bool:
        return (
            (receipt := receipts.get(event.get_user_id())) is not None
            and (reply := receipt.get_reply()) is not None
            and len(reply) > 0
            and msg.has(Reply)
            and msg[Reply, 0].id == reply[0].id
            and msg.extract_plain_text() in {"接受", "拒绝"}
        )

    @waiter.waiter(
        [milky_event.FriendMessageEvent],
        keep_session=False,
        rule=rule,
        permission=SUPERUSER,
    )
    def wait(event: milky_event.FriendMessageEvent) -> bool:
        return event.get_message().extract_plain_text() == "接受"

    if (res := await wait.wait(timeout=10 * 60)) is not None:
        await (event.accept if res else event.reject)()
    else:
        for receipt in receipts.values():
            await receipt.reply("操作超时，将忽略该好友申请")
