import random
from typing import override

from nonebot import require
from nonebot.adapters import Bot, Event, Message

require("nonebot_plugin_alconna")
require("nonebot_plugin_localstore")
from nonebot_plugin_alconna import Image, UniMessage
from nonebot_plugin_alconna.extension import Extension, add_global_extension
from nonebot_plugin_localstore import get_plugin_data_dir


class BrokenPicExtension(Extension):
    @property
    @override
    def priority(self) -> int:
        return 20

    @property
    @override
    def id(self) -> str:
        return "bot7685:broken_pic"

    @override
    async def send_wrapper(
        self,
        bot: Bot,
        event: Event,
        send: str | Message | UniMessage,
    ) -> str | Message | UniMessage:
        if isinstance(send, str):
            return send
        if isinstance(send, Message):
            send = UniMessage.generate_sync(message=send)

        send = send.copy()

        for idx, segment in enumerate(send[:]):
            if isinstance(segment, Image) and random.random() < 0.0001:
                file = random.choice(list(get_plugin_data_dir().iterdir()))
                send[idx] = Image(raw=file.read_bytes())

        return send


add_global_extension(BrokenPicExtension)
