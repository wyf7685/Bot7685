from nonebot import get_driver, on_notice, require
from nonebot.adapters.onebot.v11.event import FriendAddNoticeEvent
from nonebot.params import Depends

require("nonebot_plugin_alconna")
require("nonebot_plugin_userinfo")
from nonebot_plugin_alconna.uniseg import Target, UniMessage
from nonebot_plugin_userinfo import EventUserInfo, UserInfo


def IsFriendAdd():

    def checker(event: FriendAddNoticeEvent):
        return

    return Depends(checker)


@on_notice().handle(parameterless=[IsFriendAdd()])
async def _(info: UserInfo = EventUserInfo()):
    message = UniMessage.text(f"收到好友申请: {info.user_name}({info.user_id})\n")
    if avatar := info.user_avatar:
        message += UniMessage.image(raw=await avatar.get_image())

    for target in get_driver().config.superusers:
        await message.send(Target(target, private=True))
