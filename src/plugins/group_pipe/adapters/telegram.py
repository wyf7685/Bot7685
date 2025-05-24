from copy import deepcopy
from io import BytesIO
from typing import ClassVar, override

import anyio
from nonebot.adapters import Event as BaseEvent
from nonebot.adapters.telegram import Adapter, Bot, Message, MessageSegment
from nonebot.adapters.telegram.event import ForumTopicMessageEvent, MessageEvent
from nonebot.adapters.telegram.model import InputFile
from nonebot.adapters.telegram.model import Message as MessageModel
from nonebot_plugin_alconna import uniseg as u

from src.plugins.upload_cos import upload_cos

from ..adapter import mark
from ..utils import download_url, guess_url_type, webm_to_gif
from .common import MessageConverter as BaseMessageConverter
from .common import MessageSender as BaseMessageSender

TG_MSGID_MARK = "$telegram$"


class MessageConverter(BaseMessageConverter[MessageSegment, Bot, Message]):
    _adapter_: ClassVar[str | None] = Adapter.get_name()

    @override
    @classmethod
    def get_message(cls, event: BaseEvent) -> Message | None:
        if not isinstance(event, MessageEvent):
            return None

        message = deepcopy(event.original_message)
        if event.reply_to_message:
            msg_id = event.reply_to_message.message_id
            if (
                isinstance(event, ForumTopicMessageEvent)
                and msg_id == event.message_thread_id
            ):
                msg_id = None
            if msg_id is not None:
                chat_id = event.reply_to_message.chat.id
                reply = MessageSegment(
                    "reply",
                    {"message_id": f"{chat_id}{TG_MSGID_MARK}{msg_id}"},
                )
                message.insert(0, reply)

        return message

    @override
    @classmethod
    def get_message_id(cls, event: BaseEvent, bot: Bot) -> str:
        msg_id = super().get_message_id(event, bot)
        if not isinstance(event, MessageEvent):
            return msg_id
        chat_id = event.chat.id
        return f"{chat_id}{TG_MSGID_MARK}{msg_id}"

    @override
    async def get_reply_id(self, message_id: str) -> str | None:
        reply_id = await super().get_reply_id(message_id)
        if reply_id is not None and TG_MSGID_MARK in reply_id:
            return reply_id.partition(TG_MSGID_MARK)[2]
        return reply_id

    async def get_file_info(self, file_id: str) -> tuple[str | None, str]:
        token = self.src_bot.bot_config.token
        file_path = (await self.src_bot.get_file(file_id)).file_path
        return file_path, f"https://api.telegram.org/file/bot{token}/{file_path}"

    @override
    async def convert_reply(self, src_msg_id: str | int) -> u.Segment:
        if reply_id := await self.get_reply_id(str(src_msg_id)):
            if TG_MSGID_MARK in reply_id:
                reply_id = reply_id.partition(TG_MSGID_MARK)[2]
            return u.Reply(reply_id)

        if isinstance(src_msg_id, str) and TG_MSGID_MARK in src_msg_id:
            src_msg_id = src_msg_id.partition(TG_MSGID_MARK)[2]

        return u.Text(f"[reply:{src_msg_id}]")

    @mark("mention")
    async def mention(self, segment: MessageSegment) -> u.Segment:
        return u.Text(segment.data["text"])

    @mark("sticker", "photo")
    async def sticker(self, segment: MessageSegment) -> u.Segment:
        file_id = segment.data["file"]
        file_path, url = await self.get_file_info(file_id)
        if file_path is None:
            return u.Text(f"[image:{file_id}]")

        info = await guess_url_type(url)
        if info is None:
            return u.Text(f"[image:{file_id}]")

        if info.mime == "video/webm":
            if raw := await download_url(url):
                raw = await webm_to_gif(raw)
                return u.Image(raw=raw, mimetype="image/gif")
            return u.Text(f"[image:{info.mime}:{file_id}]")

        try:
            url = await upload_cos(url, self.get_cos_key(file_path))
        except Exception as err:
            self.logger.opt(exception=err).debug("上传文件失败")

        return u.Image(url=url, mimetype=info.mime)

    @mark("document", "video")
    async def document(self, segment: MessageSegment) -> u.Segment:
        file_id = segment.data["file"]
        file_path, url = await self.get_file_info(file_id)
        if file_path is None:
            return u.Text(f"[file:{file_id}]")

        info = await guess_url_type(url)
        if info is None:
            return u.Text(f"[file:{file_id}]")

        try:
            url = await upload_cos(url, self.get_cos_key(file_path))
        except Exception as err:
            self.logger.opt(exception=err).debug("上传文件失败")
            return u.Text(f"[file:{info.mime}:{file_id}]")

        return u.File(
            id=file_id,
            url=url,
            mimetype=info.mime,
            name=file_path.rpartition("/")[-1],
        )

    @mark("reply")
    async def reply(self, segment: MessageSegment) -> u.Segment:
        return await self.convert_reply(segment.data["message_id"])


class MessageSender(BaseMessageSender[Bot, MessageModel]):
    _adapter_: ClassVar[str | None] = Adapter.get_name()

    @override
    @staticmethod
    def extract_msg_id(data: MessageModel) -> str:
        return f"{data.chat.id}{TG_MSGID_MARK}{data.message_id}" if data else ""

    @override
    @classmethod
    async def send(
        cls,
        dst_bot: Bot,
        target: u.Target,
        msg: u.UniMessage[u.Segment],
        src_type: str | None = None,
        src_id: str | None = None,
    ) -> None:
        msg = msg.exclude(u.Keyboard) + msg.include(u.Keyboard)

        for seg in msg[u.Reply]:
            if TG_MSGID_MARK in seg.id:
                seg.id = seg.id.partition(TG_MSGID_MARK)[2]

        # alc 里没有处理 gif (animation) 的逻辑
        # 提取出来单独发送
        gif_files: list[InputFile | str] = []
        for seg in msg[u.Image]:
            if seg.mimetype == "image/gif" and (file := (seg.raw or seg.url)):
                msg.remove(seg)
                if isinstance(file, BytesIO):
                    file = file.read()
                if seg.name and isinstance(file, bytes):
                    file = (f"{seg.name}.gif", file)
                gif_files.append(file)

        await super().send(dst_bot, target, msg, src_type, src_id)

        async def _send_gif(file: InputFile | str) -> None:
            message_thread_id = target.extra.get("message_thread_id", None)
            res = await dst_bot.send_animation(
                chat_id=target.id,
                animation=file,
                message_thread_id=message_thread_id,
            )
            await cls.set_dst_id(src_type, src_id, dst_bot, res)

        if len(gif_files) == 1:
            await _send_gif(gif_files[0])
        elif gif_files:
            async with anyio.create_task_group() as tg:
                for file in gif_files:
                    tg.start_soon(_send_gif, file)
