import anyio
from nonebot import require
from nonebot.adapters.onebot.v11 import Bot
from nonebot.adapters.onebot.v11.event import GroupMessageEvent
from nonebot.typing import T_State

require("nonebot_plugin_alconna")
require("nonebot_plugin_waiter")
from nonebot_plugin_alconna import on_alconna
from nonebot_plugin_alconna.uniseg import UniMessage
from nonebot_plugin_waiter import waiter

require("src.plugins.trusted")
from src.plugins.trusted import TrustedUser


async def check_reply(event: GroupMessageEvent, state: T_State) -> bool:
    if event.reply is None:
        return False

    if (target := event.reply.sender.user_id) == event.user_id:
        return False

    state["reply"] = event.reply.message_id
    state["target_id"] = target
    return target is not None


no_shit = on_alconna("他在搬史", permission=TrustedUser, rule=check_reply)


@no_shit.handle()
async def _(bot: Bot, event: GroupMessageEvent, state: T_State) -> None:
    target: int = state["target_id"]

    await (
        UniMessage.reply(str(state["reply"]))
        .at(str(target))
        .text("被指控搬史\n")
        .text("预期禁言 1 分钟\n\n")
        .text("若3分钟内有2人发送“同意”将实施禁言")
        .send()
    )

    voted: set[int] = set()

    def _rule(e: GroupMessageEvent) -> bool:
        return (
            e.group_id == event.group_id
            and e.user_id not in ({event.user_id, target} | voted)
            and e.get_message().extract_plain_text() == "同意"
        )

    @waiter(
        [event.get_type()],
        keep_session=False,
        rule=_rule,
        block=False,
    )
    def wait(event: GroupMessageEvent) -> int:
        return event.user_id

    with anyio.move_on_after(60 * 3):
        async for user in wait():
            if user is not None:
                voted.add(user)
            if len(voted) >= 2:
                break

    if len(voted) < 2:
        await UniMessage.text("同意人数不足，取消操作").finish()

    await bot.delete_msg(message_id=state["reply"])
    await bot.set_group_ban(
        group_id=event.group_id,
        user_id=target,
        duration=60,
    )
    await UniMessage.at(str(target)).text("已被禁言").finish()
