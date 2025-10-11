from typing import TYPE_CHECKING, ClassVar, cast, override

import nonebot
from nonebot.adapters import Bot, Message, MessageSegment
from nonebot_plugin_alconna import uniseg as u

from ..adapter import MessageConverter as AbstractMessageConverter
from ..adapter import MessageSender as AbstractMessageSender
from ..database import get_reply_id, set_msg_dst_id

if TYPE_CHECKING:
    from collections.abc import Iterable

    import loguru


class MessageConverter[
    TMS: MessageSegment = MessageSegment,
    TB: Bot = Bot,
    TM: Message = Message,
](AbstractMessageConverter[TB, TM], adapter=None):
    logger: ClassVar["loguru.Logger"] = nonebot.logger.opt(colors=True)

    def get_cos_key(self, key: str) -> str:
        type_ = self.src_bot.type.lower().replace(" ", "_")
        return f"{type_}/{self.src_bot.self_id}/{key}"

    async def get_reply_id(self, message_id: str) -> str | None:
        if self.dst_bot is None:
            return None

        return await get_reply_id(
            src_adapter=self.src_bot.type,
            dst_adapter=self.dst_bot.type,
            src_id=message_id,
        ) or await get_reply_id(
            src_adapter=self.dst_bot.type,
            dst_adapter=self.src_bot.type,
            dst_id=message_id,
        )

    async def convert_reply(self, src_msg_id: str | int) -> u.Segment:
        if reply_id := await self.get_reply_id(str(src_msg_id)):
            return u.Reply(reply_id)
        return u.Text(f"[reply:{src_msg_id}]")

    @override
    async def convert(self, msg: TM) -> u.UniMessage:
        if builder := u.get_builder(self.src_bot):
            msg = cast("TM", builder.preprocess(msg))

        result = u.UniMessage()
        for seg in cast("Iterable[TMS]", msg):
            try:
                res = await self._find_fn(seg)(seg)
            except Exception as err:
                self.logger.opt(exception=err).warning("处理消息段失败")
                result.append(u.Text(f"[error:{seg.type}]"))
            else:
                if isinstance(res, list):
                    result.extend(res)
                elif res is not None:
                    result.append(res)

        return result


class MessageSender[TB: Bot, TR](AbstractMessageSender[TB], adapter=None):
    @staticmethod
    def extract_msg_id(data: TR) -> str:
        return str(data)

    @classmethod
    async def set_dst_id(
        cls,
        src_adapter: str | None,
        src_id: str | None,
        dst_bot: TB,
        data: TR,
    ) -> None:
        if src_adapter and src_id:
            await set_msg_dst_id(
                src_adapter=src_adapter,
                src_id=src_id,
                dst_adapter=dst_bot.type,
                dst_id=cls.extract_msg_id(data),
            )

    @override
    @classmethod
    async def send(
        cls,
        dst_bot: TB,
        target: u.Target,
        msg: u.UniMessage,
        src_type: str | None = None,
        src_id: str | None = None,
    ) -> None:
        receipt = await msg.send(
            target=target,
            bot=dst_bot,
            fallback=u.FallbackStrategy.ignore,
        )

        for item in receipt.msg_ids:
            await cls.set_dst_id(
                src_adapter=src_type,
                src_id=src_id,
                dst_bot=dst_bot,
                data=item,
            )
