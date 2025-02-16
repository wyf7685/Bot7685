import anyio
from nonebot import require
from nonebot.adapters.onebot.v11 import Bot
from nonebot.adapters.onebot.v11.event import GroupMessageEvent
from nonebot.matcher import Matcher
from nonebot.params import Depends

require("nonebot_plugin_alconna")
require("nonebot_plugin_localstore")
require("nonebot_plugin_waiter")
from nonebot_plugin_alconna import on_alconna
from nonebot_plugin_alconna.uniseg import UniMessage
from nonebot_plugin_localstore import get_plugin_data_dir
from nonebot_plugin_waiter import waiter

require("src.plugins.trusted")
from src.plugins.trusted import TrustedUser


def add_ban_count(user_id: int) -> int:
    file = get_plugin_data_dir() / "count" / f"{user_id}"
    file.parent.mkdir(parents=True, exist_ok=True)
    cnt = int(file.read_text()) + 1 if file.exists() else 1
    file.write_text(str(cnt))
    return cnt


no_shit = on_alconna("他在搬史", permission=TrustedUser)


async def check_reply(event: GroupMessageEvent) -> tuple[int, int]:
    if (
        event.reply is None
        or (target := event.reply.sender.user_id) is None
        or target == event.user_id
    ):
        Matcher.skip()

    return event.reply.message_id, target


@no_shit.handle()
async def _(
    bot: Bot,
    event: GroupMessageEvent,
    r: tuple[int, int] = Depends(check_reply),
) -> None:
    reply, target = r

    await (
        UniMessage.reply(str(reply))
        .at(str(target))
        .text(" 被指控搬史\n")
        .text("预期禁言 1 分钟\n\n")
        .text("若3分钟内有2人发送“同意”将实施禁言")
        .send()
    )

    voted: set[int] = set()
    should_ban = False

    def _rule(e: GroupMessageEvent) -> bool:
        return (
            e.group_id == event.group_id
            and e.user_id not in {*voted, event.user_id}
            and e.get_message().extract_plain_text().strip() == "同意"
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
            if should_ban := user == target:
                break
            if user is not None:
                voted.add(user)
            if should_ban := len(voted) >= 2:
                break

    if not should_ban:
        await UniMessage.text("同意人数不足，取消操作").finish(reply_to=True)

    await bot.delete_msg(message_id=reply)
    await bot.set_group_ban(group_id=event.group_id, user_id=target, duration=60)
    cnt = add_ban_count(target)
    await (
        UniMessage.at(str(target))
        .text(f" 已被禁言, 共计 {cnt} 次")
        .finish(reply_to=True)
    )
