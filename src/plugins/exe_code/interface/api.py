import asyncio
import functools
import json
from typing import Any, ClassVar, Dict, List, Optional

from nonebot.adapters import Bot, Event
from nonebot.exception import ActionFailed
from nonebot.log import logger
from nonebot_plugin_alconna.uniseg import Receipt, Target, UniMessage

from ..const import DESCRIPTION_RESULT_TYPE, T_Context, T_Message
from ..help_doc import descript
from ..user_const_var import T_ConstVar, default_context, load_const, set_const
from ..utils import Buffer
from .group import Group
from .interface import Interface
from .user import User
from .utils import (
    Result,
    check_message_t,
    debug_log,
    export,
    export_adapter_message,
    export_manager,
    is_super_user,
    send_forward_message,
    send_message,
)

logger = logger.opt(colors=True)


class API(Interface):
    __inst_name__: ClassVar[str] = "api"

    bot: Bot
    event: Event
    context: T_Context

    def __init__(self, bot: Bot, event: Event, context: T_Context) -> None:
        super(API, self).__init__()
        self.bot = bot
        self.event = event
        self.context = context

    @descript(
        description="调用 OneBot V11 接口",
        parameters=dict(
            api="需要调用的接口名，参考 https://github.com/botuniverse/onebot-11/blob/master/api/public.md",
            data="以命名参数形式传入的接口调用参数",
        ),
        result=DESCRIPTION_RESULT_TYPE,
    )
    @debug_log
    async def call_api(self, api: str, **data: Any) -> Result:
        res: Dict[str, Any] | List[Any]
        try:
            res = await self.bot.call_api(api, **data) or {}
        except ActionFailed as e:
            res = {"error": e}
        except BaseException as e:
            res = {"error": e}
            logger.opt(exception=e).warning(
                "用户({uin})调用api<y>{api}</y>时发生错误: <r>{err}</r>".format(
                    uin=self.event.get_user_id(),
                    api=api,
                    err=e,
                )
            )
        if isinstance(res, dict):
            res.setdefault("error", None)
        return Result(res)

    @descript(
        description="向QQ号为qid的用户发送私聊消息",
        parameters=dict(
            qid="需要发送私聊的QQ号",
            msg="发送的内容",
        ),
        result="Receipt",
    )
    @debug_log
    async def send_prv(self, qid: int | str, msg: T_Message) -> Receipt:
        return await send_message(
            bot=self.bot,
            event=self.event,
            target=Target.user(str(qid)),
            message=msg,
        )

    @descript(
        description="向群号为gid的群聊发送消息",
        parameters=dict(
            gid="需要发送消息的群号",
            msg="发送的内容",
        ),
        result="Receipt",
    )
    @debug_log
    async def send_grp(self, gid: int | str, msg: T_Message) -> Receipt:
        return await send_message(
            bot=self.bot,
            event=self.event,
            target=Target.group(str(gid)),
            message=msg,
        )

    @descript(
        description="向QQ号为qid的用户发送合并转发消息",
        parameters=dict(
            qid="需要发送消息的QQ号",
            msgs="发送的消息列表",
        ),
        result="Receipt",
    )
    @debug_log
    async def send_prv_fwd(self, qid: int | str, msgs: List[T_Message]) -> Receipt:
        return await send_forward_message(
            bot=self.bot,
            event=self.event,
            target=Target.group(str(qid)),
            msgs=msgs,
        )

    @descript(
        description="向群号为gid的群聊发送合并转发消息",
        parameters=dict(
            gid="需要发送消息的群号",
            msgs="发送的消息列表",
        ),
        result="Receipt",
    )
    @debug_log
    async def send_grp_fwd(self, gid: int | str, msgs: List[T_Message]) -> Receipt:
        return await send_forward_message(
            bot=self.bot,
            event=self.event,
            target=Target.group(str(gid)),
            msgs=msgs,
        )

    @export
    @descript(
        description="向当前会话发送合并转发消息",
        parameters=dict(msgs="发送的消息列表"),
        result="Receipt",
    )
    @debug_log
    async def send_fwd(self, msgs: List[T_Message]) -> Receipt:
        return await send_forward_message(
            bot=self.bot,
            event=self.event,
            target=None,
            msgs=msgs,
        )

    @export
    @descript(
        description="获取用户对象",
        parameters=dict(qid="用户QQ号"),
        result="User对象",
    )
    def user(self, qid: str) -> "User":
        return User(self, qid)

    @export
    @descript(
        description="获取群聊对象",
        parameters=dict(gid="群号"),
        result="Group对象",
    )
    def group(self, gid: str) -> "Group":
        return Group(self, gid)

    @export
    @descript(
        description="向当前会话发送消息",
        parameters=dict(
            msg="需要发送的消息",
        ),
        result="Receipt",
    )
    @debug_log
    async def feedback(self, msg: T_Message) -> Receipt:
        if not check_message_t(msg):
            msg = str(msg)

        return await send_message(
            bot=self.bot,
            event=self.event,
            target=None,
            message=msg,
        )

    @descript(
        description="撤回指定消息",
        parameters=dict(
            msg="需要撤回的消息ID，可通过Result获取",
        ),
        result=DESCRIPTION_RESULT_TYPE,
    )
    @debug_log
    async def recall(self, msg_id: int) -> Result:
        if "OneBot" in self.bot.type:
            return await self.call_api("delete_msg", message_id=msg_id)
        raise NotImplementedError

    @descript(
        description="判断当前会话是否为群聊",
        parameters=None,
        result="当前会话为群聊返回True，否则返回False",
    )
    @debug_log
    def is_group(self) -> bool:
        return not UniMessage.get_target(self.event, self.bot).private

    @descript(
        description="设置环境常量，在每次执行代码时加载",
        parameters=dict(
            name="设置的环境变量名",
            value="设置的环境常量，仅允许输入可被json序列化的对象，留空则为删除",
        ),
        result=None,
    )
    @debug_log
    def set_const(self, name: str, value: Optional[T_ConstVar] = None) -> None:
        if value is None:
            set_const(self.event.get_user_id(), name)
            return

        try:
            json.dumps([value])
        except ValueError as e:
            raise TypeError("设置常量的类型必须是可被json序列化的对象") from e

        set_const(self.event.get_user_id(), name, value)

    @export
    @debug_log
    def print(self, *args, sep: str = " ", end: str = "\n", **_):
        Buffer(self.event.get_user_id()).write(sep.join(str(i) for i in args) + end)

    @export
    @descript(
        description="向当前会话发送API说明(本文档)",
        parameters=None,
        result=None,
    )
    @debug_log
    async def help(self) -> None:
        content, description = type(self).get_all_description()
        msgs = [
            "   ====API说明====   ",
            " - API说明文档 - 目录 - \n" + "\n".join(content),
            *description,
        ]
        await send_forward_message(self.bot, self.event, None, msgs)

    @export
    @descript(
        description="在执行代码时等待",
        parameters=dict(seconds="等待的时间，单位秒"),
        result=None,
    )
    @debug_log
    async def sleep(self, seconds: float) -> None:
        await asyncio.sleep(seconds)

    @export
    @descript(
        description="重置环境",
        parameters=None,
        result=None,
    )
    @debug_log
    def reset(self) -> None:
        self.context.clear()
        self.context.update(default_context)
        self.context.update(load_const(self.event.get_user_id()))
        self.export_to(self.context)

    def export_to(self, context: T_Context) -> None:
        super(API, self).export_to(context)

        context["qid"] = self.event.get_user_id()
        context["usr"] = self.user(context["qid"])
        context["gid"] = str(getattr(self.event, "group_id", "")) or None
        context["grp"] = self.group(context["gid"]) if context["gid"] else None
        export_adapter_message(context, self.event)

        if is_super_user(self.bot, self.event):
            export_manager(context)

    def __getattr__(self, name: str):
        if name.startswith("__") and name.endswith("__"):
            raise AttributeError(
                f"'{self.__class__.__name__}' object has no attribute '{name}'"
            )
        return functools.partial(self.call_api, name)

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}(user_id={self.event.get_user_id()})"
