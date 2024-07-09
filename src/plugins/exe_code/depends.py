from typing import Annotated
from nonebot.adapters import Bot, Event, Message
from nonebot.matcher import Matcher
from nonebot.params import Depends
from nonebot.rule import Rule
from nonebot_plugin_alconna.uniseg import MsgTarget, UniMessage, UniMsg, reply_fetch
from nonebot_plugin_alconna.uniseg.segment import At, Image, Reply, Text
from nonebot_plugin_session import EventSession

from .config import cfg


def ExeCodeEnabled() -> Rule:
    try:
        from nonebot.adapters.console import Bot as ConsoleBot
    except ImportError:
        ConsoleBot = None

    def check(bot: Bot, session: EventSession, target: MsgTarget):
        if ConsoleBot is not None and isinstance(bot, ConsoleBot):
            return True

        return (session.id1 or "") in cfg.user or (
            not target.private and str(target.id) in cfg.group
        )

    return Rule(check)


def _ExtractCode():

    def extract_code(msg: UniMsg) -> str:
        code = ""
        for seg in msg:
            if isinstance(seg, Text):
                code += seg.text
            elif isinstance(seg, At):
                code += f'"{seg.target}"'
            elif isinstance(seg, Image):
                code += f'"{seg.url or "[url]"}"'
        return code.removeprefix("code").strip()

    return Depends(extract_code)


def _EventTarget():

    async def event_target(event: Event, msg: UniMsg) -> str:
        uin = event.get_user_id()
        if msg.has(At):
            uin = msg[At, 0].target
        return uin

    return Depends(event_target)


def _EventImage():

    async def event_image(msg: UniMsg) -> Image:
        if msg.has(Image):
            return msg[Image, 0]
        elif msg.has(Reply):
            reply_msg = msg[Reply, 0].msg
            if isinstance(reply_msg, Message):
                return await event_image(await UniMessage.generate(message=reply_msg))
        Matcher.skip()

    return Depends(event_image)


def _EventReply():

    async def event_reply(event: Event, bot: Bot) -> Reply:
        if reply := await reply_fetch(event, bot):
            return reply
        Matcher.skip()

    return Depends(event_reply)


def _EventReplyMessage():

    async def event_reply_message(event: Event, reply: EventReply) -> Message:
        if not (msg := reply.msg):
            Matcher.skip()

        if not isinstance(msg, Message):
            msg = type(event.get_message())(msg)

        return msg

    return Depends(event_reply_message)


EXECODE_ENABLED = ExeCodeEnabled()
ExtractCode = Annotated[str, _ExtractCode()]
EventTarget = Annotated[str, _EventTarget()]
EventImage = Annotated[Image, _EventImage()]
EventReply = Annotated[Reply, _EventReply()]
EventReplyMessage = Annotated[Message, _EventReplyMessage()]
