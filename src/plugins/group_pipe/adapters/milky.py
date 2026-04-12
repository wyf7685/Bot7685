import json
from copy import deepcopy
from typing import Any, override

from nonebot.adapters import Event as BaseEvent
from nonebot.adapters.milky import Adapter, Bot, Message, MessageSegment
from nonebot.adapters.milky.event import MessageEvent
from nonebot.adapters.milky.model.api import MessageResponse
from nonebot_plugin_alconna import uniseg as u

from src.plugins.cache import get_cache

from ..adapter import converts
from ..utils import guess_url_type
from .common import MessageConverter as BaseMessageConverter
from .common import MessageSender as BaseMessageSender

file_cache = get_cache[str](namespace="group_pipe:milky:file")


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
            file_id: str = file_seg.data.get("file_id", "")
            file_name: str = file_seg.data.get("file_name", "")
            file_data: dict[str, Any] = {"file_id": file_id, "file_name": file_name}
            if event.data.message_scene == "group":
                file_data["method"] = "get_group_file_download_url"
                file_data["group_id"] = event.data.peer_id
            elif event.data.message_scene == "friend":
                file_data["method"] = "get_private_file_download_url"
                file_data["user_id"] = event.data.sender_id
                file_data["file_hash"] = file_id.split("_")[0]
            await file_cache.set(file_id, json.dumps(file_data))

        return message

    @converts("file")
    async def file(self, segment: MessageSegment) -> u.Segment | None:
        file_info = segment.data
        file_id = file_info.get("file_id")
        if not file_id:
            return None

        file_data_json = await file_cache.get(file_id)
        if not file_data_json:
            return None

        file_data: dict[str, Any] = json.loads(file_data_json)
        file_name = file_data.pop("file_name")
        method = getattr(self.src_bot, file_data.pop("method"), None)
        if method is None:
            return None

        url: str = await method(**file_data)
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
