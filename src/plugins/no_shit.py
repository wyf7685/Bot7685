import json
from typing import Annotated

import anyio
from nonebot import require
from nonebot.adapters.onebot.v11 import Bot
from nonebot.adapters.onebot.v11.event import GroupMessageEvent
from nonebot.matcher import Matcher
from nonebot.params import Depends

require("nonebot_plugin_alconna")
require("nonebot_plugin_htmlrender")
require("nonebot_plugin_localstore")
require("nonebot_plugin_waiter")
from nonebot_plugin_alconna import on_alconna
from nonebot_plugin_alconna.uniseg import UniMessage
from nonebot_plugin_htmlrender import md_to_pic
from nonebot_plugin_localstore import get_plugin_data_file
from nonebot_plugin_waiter import waiter

require("src.plugins.trusted")
from src.plugins.trusted import TrustedUser


def add_ban_count(group_id: int, user_id: int) -> int:
    file = get_plugin_data_file(f"{group_id}.json")
    data: dict[str, int] = json.loads(file.read_text())
    cnt = data[str(user_id)] = data.get(str(user_id), 0) + 1
    file.write_text(json.dumps(data))
    return cnt


no_shit = on_alconna("他在搬史", permission=TrustedUser())
shit_rank = on_alconna("搬史榜", permission=TrustedUser())


async def check_reply(event: GroupMessageEvent) -> tuple[int, int]:
    if (
        event.reply is None
        or (target := event.reply.sender.user_id) is None
        or target == event.user_id
    ):
        Matcher.skip()

    return event.reply.message_id, target


Reply = Annotated[tuple[int, int], Depends(check_reply)]


@no_shit.handle()
async def _(bot: Bot, event: GroupMessageEvent, r: Reply) -> None:
    reply, target = r

    await (
        UniMessage.reply(str(reply))
        .at(str(target))
        .text(" 被指控搬史\n")
        .text("预期禁言 5x(同意人数) 分钟\n\n")
        .text("期限5分钟, 请发表您宝贵的意见")
        .send()
    )

    voted: set[int] = set()

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

    target_vote = False
    with anyio.move_on_after(60 * 5):
        async for user in wait():
            if target_vote := user == target:
                break
            if user is not None:
                voted.add(user)

    if not voted:
        await UniMessage.text("没有人认为他在搬史, 取消操作").finish(reply_to=True)

    msg = UniMessage.text(f"同意人数: {len(voted)}\n预期禁言{5 * len(voted)} 分钟")
    if target_vote:
        msg = UniMessage.text("被举报者自首, 立即执行\n") + msg
    await msg.send(reply_to=True)

    await bot.delete_msg(message_id=reply)
    await bot.set_group_ban(
        group_id=event.group_id,
        user_id=target,
        duration=60 * 5 * len(voted),
    )
    cnt = add_ban_count(event.group_id, target)
    await (
        UniMessage.at(str(target))
        .text(f" 已被禁言, 共计 {cnt} 次")
        .finish(reply_to=True)
    )


@shit_rank.handle()
async def _(event: GroupMessageEvent) -> None:
    file = get_plugin_data_file(f"{event.group_id}.json")
    if not file.exists():
        await UniMessage.text("暂无记录").finish()

    data: dict[str, int] = json.loads(file.read_text())

    table = "<table>"
    for user_id, cnt in sorted(data.items(), key=lambda x: x[1], reverse=True):
        avatar_url = f"http://thirdqq.qlogo.cn/headimg_dl?dst_uin={user_id}&spec=640"
        avatar = f'<td><picture><img src="{avatar_url}" /></picture></td>'
        text = f"<td>{user_id}<br/>共计 {cnt} 次</td>"
        table += f"<tr>{avatar}{text}</tr>"
    table += "</table>"

    md = "## 搬史榜\n\n" + table
    pic = await md_to_pic(md)
    await UniMessage.image(raw=pic).send()
