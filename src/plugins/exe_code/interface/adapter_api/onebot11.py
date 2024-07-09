from typing import ClassVar

from ..api import API as BaseAPI
from ..api import register_api
from ..help_doc import descript
from ..utils import Result, debug_log, export

try:
    from nonebot.adapters.onebot.v11 import Bot

    @register_api(Bot)
    class API(BaseAPI):
        __inst_name__: ClassVar[str] = "api"

        @export
        @descript(
            description="[OneBotV11] 撤回指定消息",
            parameters=dict(msg_id="需要撤回的消息ID，可通过Result获取"),
        )
        @debug_log
        async def recall(self, msg_id: int) -> Result:
            return await self.call_api("delete_msg", message_id=msg_id)

        @export
        @descript(
            description="[OneBotV11] 通过消息ID获取指定消息",
            parameters=dict(msg_id="需要获取的消息ID，可通过getmid获取"),
        )
        @debug_log
        async def get_msg(self, msg_id: int) -> Result:
            return await self.call_api("get_msg", message_id=msg_id)

        @export
        @descript(
            description="[OneBotV11] 通过合并转发ID获取合并转发消息",
            parameters=dict(msg_id="需要获取的合并转发ID，可通过getcqcode获取"),
        )
        @debug_log
        async def get_fwd(self, msg_id: int) -> Result:
            return await self.call_api("get_forward_msg", message_id=msg_id)

except ImportError:
    pass
