from nonebot_plugin_alconna import UniMessage


class MessageProcessor:
    @classmethod
    async def process(cls, msg: UniMessage) -> UniMessage:
        return msg
