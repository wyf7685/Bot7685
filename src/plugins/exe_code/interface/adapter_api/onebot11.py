from typing import ClassVar

from ..api import API as BaseAPI
from ..api import register_api
from ..help_doc import descript, type_alias
from ..utils import Result, debug_log, export

try:
    from nonebot.adapters.onebot.v11 import Adapter, Message

    type_alias[Message] = "Message"

    @register_api(Adapter)
    class API(BaseAPI):
        __inst_name__: ClassVar[str] = "api"

        @export
        @descript(
            description="撤回指定消息",
            parameters=dict(msg_id="需要撤回的消息ID，可通过Result/getmid获取"),
        )
        @debug_log
        async def recall(self, msg_id: int) -> Result:
            return await self.call_api(
                "delete_msg",
                message_id=msg_id,
                raise_text="撤回消息失败",
            )

        @export
        @descript(
            description="通过消息ID获取指定消息",
            parameters=dict(msg_id="需要获取的消息ID，可通过getmid获取"),
            result="获取到的消息",
        )
        @debug_log
        async def get_msg(self, msg_id: int) -> Message:
            res = await self.call_api(
                "get_msg",
                message_id=msg_id,
                raise_text="获取消息失败",
            )
            return Message(res["raw_message"])

        @export
        @descript(
            description="通过合并转发ID获取合并转发消息",
            parameters=dict(msg_id="需要获取的合并转发ID，可通过getcqcode获取"),
            result="获取到的合并转发消息列表",
        )
        @debug_log
        async def get_fwd(self, msg_id: int) -> list[Message]:
            res = await self.call_api(
                "get_msg",
                message_id=msg_id,
                raise_text="获取合并转发消息失败",
            )
            return [Message(i["raw_message"]) for i in res["messages"]]

except ImportError:
    pass
