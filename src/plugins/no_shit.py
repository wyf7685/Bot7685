import json
from datetime import datetime, timedelta
from typing import Annotated

import anyio
from nonebot import on_type, require
from nonebot.adapters.onebot.v11 import Bot
from nonebot.adapters.onebot.v11.event import GroupBanNoticeEvent, GroupMessageEvent
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

require("src.plugins.cache")
require("src.plugins.trusted")
from src.plugins.cache import get_cache
from src.plugins.trusted import TrustedUser

ban_time_cache = get_cache[str, datetime]("no_shit.ban_time")


def add_ban_count(group_id: int, user_id: int) -> int:
    file = get_plugin_data_file(f"{group_id}.json")
    data: dict[str, int] = json.loads(file.read_text())
    cnt = data[str(user_id)] = data.get(str(user_id), 0) + 1
    file.write_text(json.dumps(data))
    return cnt


async def check_reply(event: GroupMessageEvent) -> tuple[int, int]:
    if (
        event.reply is None
        or (target := event.reply.sender.user_id) is None
        or target == event.user_id
    ):
        Matcher.skip()

    return event.reply.message_id, target


Reply = Annotated[tuple[int, int], Depends(check_reply)]

no_shit = on_alconna("他在搬史", permission=TrustedUser())


@no_shit.handle()
async def _(bot: Bot, event: GroupMessageEvent, r: Reply) -> None:
    reply_msg_id, target = r

    await (
        UniMessage.reply(str(reply_msg_id))
        .at(str(target))
        .text(" 被指控搬史\n")
        .text("预期禁言 (同意人数) 分钟\n\n")
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

    with anyio.move_on_after(60 * 5):
        async for user in wait():
            if user == target:
                break
            if user is not None:
                voted.add(user)

    if not voted:
        await UniMessage.text("没有人认为他在搬史, 取消操作").finish(reply_to=True)

    cache_key = f"{event.group_id}:{target}"
    last_ban_end = await ban_time_cache.get(cache_key, None)
    now = datetime.now()
    current_remaining = (
        (last_ban_end - now).total_seconds()
        if last_ban_end and now < last_ban_end
        else 0
    )
    expected_secs = min(len(voted) * 60.0 + current_remaining, 5 * 60.0)
    msg = f"同意人数: {len(voted)}\n预期禁言 {expected_secs / 60:.2f} 分钟"
    await UniMessage.text(msg).send(reply_to=True)

    await bot.delete_msg(message_id=reply_msg_id)
    await bot.set_group_ban(
        group_id=event.group_id,
        user_id=target,
        duration=int(expected_secs),
    )
    await ban_time_cache.set(
        cache_key,
        now + timedelta(seconds=expected_secs),
        ttl=expected_secs,
    )

    cnt = add_ban_count(event.group_id, target)
    await (
        UniMessage.at(str(target))
        .text(f" 已被禁言, 共计 {cnt} 次")
        .finish(reply_to=True)
    )


async def _check_liftban(event: GroupBanNoticeEvent) -> bool:
    return event.sub_type == "lift_ban"


on_liftban = on_type(GroupBanNoticeEvent, rule=_check_liftban)


@on_liftban.handle()
async def _(event: GroupBanNoticeEvent) -> None:
    cache_key = f"{event.group_id}:{event.user_id}"
    if await ban_time_cache.exists(cache_key):
        await ban_time_cache.delete(cache_key)


RANK_TEMPLATE = """## 搬史榜\n\n<table>{table}</table>"""
TABLE_ROW_TEMPLATE = """\
<tr><td style="height:64px;width:64px"><picture>\
<img src="http://thirdqq.qlogo.cn/headimg_dl?dst_uin={user_id}&spec=640" />\
</picture></td><td>{user_id}<br/>共计 {count} 次</td></tr>\
"""

shit_rank = on_alconna("搬史榜", permission=TrustedUser())


@shit_rank.handle()
async def _(event: GroupMessageEvent) -> None:
    file = get_plugin_data_file(f"{event.group_id}.json")
    if not file.exists():
        await UniMessage.text("暂无记录").finish()

    data: dict[str, int] = json.loads(file.read_text())
    md = RANK_TEMPLATE.format(
        table="".join(
            TABLE_ROW_TEMPLATE.format(count=count, user_id=user_id)
            for user_id, count in sorted(data.items(), key=lambda x: x[1], reverse=True)
        )
    )
    pic = await md_to_pic(md)
    await UniMessage.image(raw=pic).send()
