from nonebot.adapters import Bot, Event, Message
from nonebot.matcher import Matcher
from nonebot.params import Depends
from nonebot.rule import Rule
from nonebot_plugin_alconna.uniseg import UniMessage, UniMsg, reply_fetch, MsgTarget
from nonebot_plugin_alconna.uniseg.segment import At as UniAt
from nonebot_plugin_alconna.uniseg.segment import Image as UniImage
from nonebot_plugin_alconna.uniseg.segment import Reply as UniReply
from nonebot_plugin_alconna.uniseg.segment import Text as UniText

from .config import cfg


def ExeCodeEnabled():
    try:
        from nonebot.adapters.console import Bot as ConsoleBot
    except ImportError:
        ConsoleBot = None

    def check(bot: Bot, event: Event, target: MsgTarget):
        if ConsoleBot is not None and isinstance(bot, ConsoleBot):
            return True

        return event.get_user_id() in cfg.user or (
            not target.private and str(target.id) in cfg.group
        )

    return Rule(check)


EXECODE_ENABLED = ExeCodeEnabled()


def ExtractCode():
    def extract_code(msg: UniMsg):
        code = ""
        for seg in msg:
            if isinstance(seg, UniText):
                code += seg.text
            elif isinstance(seg, UniAt):
                code += f'"{seg.target}"'
            elif isinstance(seg, UniImage) and seg.url:
                code += f'"{seg.url}"'
        return code.removeprefix("code").strip()

    return Depends(extract_code)


def EventReplyMessage(allow_empty: bool = True):
    async def event_reply_message(event: Event, bot: Bot):
        if not (reply := await reply_fetch(event, bot)) or not (msg := reply.msg):
            if allow_empty:
                return None
            Matcher.skip()

        if not isinstance(msg, Message):
            msg = event.get_message().__class__(msg)

        return await UniMessage.generate(message=msg)

    return Depends(event_reply_message)


def EventImage():
    async def event_message(msg: UniMsg) -> UniImage:
        if msg.has(UniImage):
            return msg[UniImage, 0]
        elif msg.has(UniReply):
            reply_msg = msg[UniReply, 0].msg
            if isinstance(reply_msg, Message):
                return await event_message(await UniMessage.generate(message=reply_msg))
        Matcher.skip()

    return Depends(event_message)
