from datetime import timedelta
from typing import Literal, override

from nonebot import on_notice, on_startswith
from nonebot.adapters.onebot.v11 import Adapter as OneBotV11Adapter
from nonebot.adapters.onebot.v11 import Bot, MessageEvent, MessageSegment
from nonebot.adapters.onebot.v11.event import NoticeEvent, GroupMessageEvent
from nonebot.log import logger
from nonebot.matcher import Matcher
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


def handle_response(msg_id: int, user_id: int, item: Data) -> type[Matcher]:
    logger.debug(f"{msg_id=}, {user_id=}, {item=}")

    emoji_weight_actions = {
        76: (+5, "增加"),  # 大拇指
        265: (-5, "减少"),  # 老人手机
    }

    async def rule(event: GroupMsgEmojiLikeEvent, state: T_State) -> bool:
        # 仅处理对应消息上的表情回应
        if event.message_id != msg_id:
            return False

        is_event_user = event.user_id == user_id
        cache: dict[int, int] = state.setdefault("like_cache", {})
        likes: dict[int, int] = {int(i.emoji_id): i.count for i in event.likes}
        for k, v in likes.items():
            if (
                (k not in cache or cache[k] < v)  # 判断新增表情回应
                and is_event_user  # 判断是否为触发黍泡泡的用户
                and k in emoji_weight_actions  # 判断是否为指定表情
            ):
                state["emoji_id"] = k
                return True
        else:
            # 不符合上述条件, 更新表情回应缓存
            cache.clear()
            cache.update(likes)
            return False

    async def handler(state: T_State):
        weight, action = emoji_weight_actions.get(state["emoji_id"], (0, ""))
        if weight:
            item.add_weight(weight)
            msg = f"黍泡泡 [<le>{item.text}</le>] 权重{action} {abs(weight)}, 当前权重: <c>{item.weight}</c>"
            logger.opt(colors=True).info(msg)

    return on_notice(
        rule=rule,
        handlers=[handler],
        temp=True,
        expire_time=timedelta(seconds=30),
    )


@on_startswith(("抽黍泡泡", "黍泡泡")).handle()
async def _(bot: Bot, event: MessageEvent):
    item = Data.choose()
    img = MessageSegment.image(file=str(url.with_query({"key": item.name})))
    img.data["summary"] = item.text
    send_result = await bot.send(event, MessageSegment.reply(event.message_id) + img)
    if isinstance(event, GroupMessageEvent):
        # 此处消息ID+1 为 NapCatQQ 的逻辑问题
        # 获取的消息ID与表情回应的上报ID不一致, 差值为 1
        # 暂时使用该方法纠正, 等 NapCatQQ 修复后再修改
        matcher = handle_response(send_result["message_id"] + 1, event.user_id, item)
        logger.debug(f"创建 Callback: {matcher}")
