from datetime import timedelta
from typing import Literal, override

from nonebot import on_notice, on_startswith
from nonebot.adapters.onebot.v11 import (
    Bot,
    MessageEvent,
    MessageSegment,
    Adapter as OneBotV11Adapter,
)
from nonebot.adapters.onebot.v11.event import NoticeEvent
from nonebot.log import logger
from nonebot.typing import T_State
from pydantic import BaseModel
from .data import Data
from .router import setup_router

url = setup_router()


class GroupMsgEmojiLikeEvent(NoticeEvent):
    class Like(BaseModel):
        emoji_id: str
        count: int

    notice_type: Literal["group_msg_emoji_like"]  # type: ignore
    user_id: int
    group_id: int
    message_id: int
    likes: list[Like]

    @override
    def get_user_id(self) -> str:
        return str(self.user_id)

    @override
    def get_session_id(self) -> str:
        return f"group_{self.group_id}_{self.user_id}"


OneBotV11Adapter.add_custom_model(GroupMsgEmojiLikeEvent)


def handle_response(msg_id: int, user_id: int, item: Data) -> None:
    # 表情回应缓存
    cache: dict[int, int] = {}

    async def rule(event: NoticeEvent, state: T_State) -> bool:
        # 仅接收 group_msg_emoji_like 事件
        if event.notice_type != "group_msg_emoji_like":
            return False

        # 仅处理对应消息上的表情回应
        notice_data = event.model_dump()
        if notice_data.get("message_id") != msg_id:
            return False

        is_event_user = notice_data.get("user_id") == user_id
        likes: dict[int, int] = {
            int(i["emoji_id"]): i["count"] for i in notice_data.get("likes", [])
        }
        for k, v in likes.items():
            if (
                (k not in cache or cache[k] < v)  # 判断新增表情回应
                and is_event_user  # 判断是否为触发黍泡泡的用户
                and k in {76, 265}  # 判断是否为指定表情
            ):
                state["emoji_id"] = k
                return True
        else:
            # 不符合上述条件, 更新表情回应缓存
            cache.clear()
            cache.update(likes)
            return False

    @on_notice(rule=rule, temp=True, expire_time=timedelta(minutes=3)).handle()
    async def _(state: T_State):
        weight, action = {
            76: (+1, "增加"),  # 大拇指
            265: (-1, "减少"),  # 老人手机
        }.get(state["emoji_id"], (0, ""))
        if weight:
            item.add_weight(weight)
            msg = f"黍泡泡 [<le>{item.text}</le>] 权重{action} 1, 当前权重: <c>{item.weight}</c>"
            logger.opt(colors=True).info(msg)


@on_startswith(("抽黍泡泡", "黍泡泡")).handle()
async def _(bot: Bot, event: MessageEvent):
    item = Data.choose()
    img = MessageSegment.image(file=str(url.with_query({"key": item.name})))
    img.data["summary"] = item.text
    send_result = await bot.send(event, MessageSegment.reply(event.message_id) + img)
    handle_response(send_result["message_id"], event.user_id, item)
