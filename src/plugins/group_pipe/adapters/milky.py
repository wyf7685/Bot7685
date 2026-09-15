from copy import deepcopy
from typing import override

from nonebot.adapters import Event as BaseEvent
from nonebot.adapters.milky import Adapter, Bot, Message, MessageSegment
from nonebot.adapters.milky.event import MessageEvent
from nonebot.adapters.milky.model.api import MessageResponse
from nonebot_plugin_alconna import uniseg as u

from ..adapter import converts
from ..utils import guess_url_type
from .common import MessageConverter as BaseMessageConverter
from .common import MessageSender as BaseMessageSender

_FILE_SCENE_KEY = "_group_pipe_message_scene"
_FILE_PEER_ID_KEY = "_group_pipe_peer_id"


class MessageConverter(
    BaseMessageConverter[MessageSegment, Bot, Message],
    adapter=Adapter.get_name(),
):
    @override
    @classmethod
    async def get_message(cls, event: BaseEvent) -> Message | None:
        if not isinstance(event, MessageEvent):
            return None

        message = deepcopy(event.original_message)
        for file_seg in message.get("file"):
            file_seg.data[_FILE_SCENE_KEY] = event.data.message_scene
            file_seg.data[_FILE_PEER_ID_KEY] = event.data.peer_id

        return message

    @converts("file")
    async def file(self, segment: MessageSegment) -> u.Segment | None:
        file_info = segment.data
        file_id = file_info.get("file_id")
        if not isinstance(file_id, str) or not file_id:
            return None

        file_name = file_info.get("file_name")
        if not isinstance(file_name, str) or not file_name:
            file_name = file_id

        peer_id = file_info.get(_FILE_PEER_ID_KEY)
        if not isinstance(peer_id, int):
            return u.Text(f"[file:{file_name}]")

        match file_info.get(_FILE_SCENE_KEY):
            case "group":
                url = await self.src_bot.get_group_file_download_url(
                    group_id=peer_id,
                    file_id=file_id,
                )
            case "friend":
                file_hash = file_info.get("file_hash")
                if not isinstance(file_hash, str) or not file_hash:
                    return u.Text(f"[file:{file_name}]")
                url = await self.src_bot.get_private_file_download_url(
                    user_id=peer_id,
                    file_id=file_id,
                    file_hash=file_hash,
                )
            case _:
                return u.Text(f"[file:{file_name}]")

        info = await guess_url_type(url)
        if info and info.mime.startswith("image/"):
            return u.Image(id=file_id, url=url, mimetype=info.mime, name=file_name)
        return u.File(id=file_id, url=url, mimetype=info and info.mime, name=file_name)


class MessageSender(
    BaseMessageSender[Bot, MessageResponse],
    adapter=Adapter.get_name(),
):
    @override
    @staticmethod
    def extract_msg_id(data: MessageResponse) -> str:
        return str(data.message_seq)
