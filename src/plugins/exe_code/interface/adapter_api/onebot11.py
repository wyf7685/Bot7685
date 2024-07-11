import functools
from typing import Any, Optional

from nonebot.log import logger

from ..api import API as BaseAPI
from ..api import register_api
from ..help_doc import descript, type_alias
from ..utils import Result, debug_log, export

logger = logger.opt(colors=True)


try:
    from nonebot.adapters.onebot.v11 import ActionFailed, Adapter, Message

    type_alias[Message] = "Message"

    @register_api(Adapter)
    class API(BaseAPI):
        @descript(
            description="调用 OneBot V11 接口",
            parameters=dict(
                api=(
                    "需要调用的接口名，参考"
                    " https://github.com/botuniverse/onebot-11/blob/master/api/public.md"
                ),
                data="以命名参数形式传入的接口调用参数",
            ),
            ignore={"raise_text"},
        )
        @debug_log
        async def call_api(
            self,
            api: str,
            *,
            raise_text: Optional[str] = None,
            **data: Any,
        ) -> Result:
            res: dict[str, Any] | list[Any] | None
            try:
                res = await self.bot.call_api(api, **data)
            except ActionFailed as e:
                res = {"error": e}
            except BaseException as e:
                res = {"error": e}
                msg = f"用户({self.qid})调用api<y>{api}</y>时发生错误: <r>{e}</r>"
                logger.opt(exception=e).warning(msg)
            if isinstance(res, dict):
                res.setdefault("error", None)

            result = Result(res)
            if result.error is not None and raise_text is not None:
                raise RuntimeError(raise_text) from result.error
            return result

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

        def __getattr__(self, name: str):
            if name.startswith("__") and name.endswith("__"):
                raise AttributeError(
                    f"'{self.__class__.__name__}' object has no attribute '{name}'"
                )
            return functools.partial(self.call_api, name)

except ImportError:
    pass
