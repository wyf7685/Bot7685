import contextlib

import nonebot_plugin_waiter as waiter
from nonebot import get_driver, on_type
from nonebot.adapters.milky import Bot
from nonebot.adapters.milky.event import FriendMessageEvent, FriendRequestEvent
from nonebot.permission import SUPERUSER
from nonebot_plugin_alconna.uniseg import Receipt, Reply, Target, UniMessage, UniMsg
from nonebot_plugin_uninfo import Uninfo


@on_type(FriendRequestEvent).handle()
async def handle_milky(
    bot: Bot,
    event: FriendRequestEvent,
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

    async def rule(event: FriendMessageEvent, msg: UniMsg) -> bool:
        return (
            (receipt := receipts.get(event.get_user_id())) is not None
            and (reply := receipt.get_reply()) is not None
            and len(reply) > 0
            and msg.has(Reply)
            and msg[Reply, 0].id == reply[0].id
            and msg.extract_plain_text() in {"接受", "拒绝"}
        )

    @waiter.waiter(
        [FriendMessageEvent],
        keep_session=False,
        rule=rule,
        permission=SUPERUSER,
    )
    def wait(event: FriendMessageEvent) -> bool:
        return event.get_message().extract_plain_text() == "接受"

    if (res := await wait.wait(timeout=10 * 60)) is not None:
        await (event.accept if res else event.reject)()
    else:
        for receipt in receipts.values():
            await receipt.reply("操作超时，将忽略该好友申请")
