import asyncio
import functools
import importlib
import json
from typing import (
    Any,
    Callable,
    ClassVar,
    Dict,
    List,
    Optional,
    ParamSpec,
    Tuple,
    TypeVar,
)

from nonebot.adapters import Bot, Event
from nonebot.exception import ActionFailed
from nonebot.log import logger
from nonebot_plugin_alconna.uniseg import Receipt, Target
from nonebot_plugin_saa import TargetQQGroup, TargetQQPrivate, extract_target

from .const import (
    DESCRIPTION_RESULT_TYPE,
    INTERFACE_EXPORT_METHOD,
    INTERFACE_INST_NAME,
    INTERFACE_METHOD_DESCRIPTION,
    T_Context,
    T_Message,
)
from .help_doc import FuncDescription, descript
from .user_const_var import T_ConstVar, default_context, load_const, set_const
from .utils import Buffer, Result, check_message_t, send_forward_message, send_message

logger = logger.opt(colors=True)

P = ParamSpec("P")
R = TypeVar("R")


def export(call: Callable[P, R]) -> Callable[P, R]:
    """将一个方法标记为导出函数"""
    setattr(call, INTERFACE_EXPORT_METHOD, True)
    return call


def is_export_method(call: Callable) -> bool:
    return getattr(call, INTERFACE_EXPORT_METHOD, False)


def is_super_user(bot: Bot, event: Event) -> bool:
    user_id = event.get_user_id()
    return (
        f"{bot.adapter.get_name().split(maxsplit=1)[0].lower()}:{user_id}"
        in bot.config.superusers
        or user_id in bot.config.superusers
    )


class InterfaceMeta(type):
    __interface_map__: ClassVar[Dict[str, "InterfaceMeta"]] = {}

    __export_method__: List[str]
    __method_description__: Dict[str, str]

    def __new__(cls, name: str, bases: tuple, attrs: Dict[str, object]):
        if name in cls.__interface_map__:
            raise TypeError(f"Interface {name} already exists")

        interface_cls = super(InterfaceMeta, cls).__new__(cls, name, bases, attrs)
        attr = interface_cls.__dict__

        # export
        interface_cls.__export_method__ = [
            k for k, v in attr.items() if getattr(v, INTERFACE_EXPORT_METHOD, False)
        ]

        # description
        interface_cls.__method_description__ = {
            k: desc
            for k, v in attr.items()
            if (desc := getattr(v, INTERFACE_METHOD_DESCRIPTION, None))
        }

        # inst_name
        if INTERFACE_INST_NAME not in attr:
            setattr(interface_cls, INTERFACE_INST_NAME, name.lower())

        # store interface class
        cls.__interface_map__[name] = interface_cls

        return interface_cls

    @classmethod
    def get_all_description(cls) -> Tuple[List[str], List[str]]:
        content: List[str] = []
        result: List[str] = []

        methods: List[Tuple[bool, str, str, FuncDescription]] = []
        for _, cls_obj in cls.__interface_map__.items():
            inst_name: str = getattr(cls_obj, INTERFACE_INST_NAME)
            description: Dict[str, FuncDescription] = getattr(
                cls_obj, INTERFACE_METHOD_DESCRIPTION
            )
            for func_name, desc in description.items():
                is_export = is_export_method(getattr(cls_obj, func_name))
                methods.append((is_export, inst_name, func_name, desc))
        methods.sort(key=lambda x: (1 - x[0], x[1], x[2]))

        for index, (is_export, inst_name, func_name, desc) in enumerate(methods, 1):
            prefix = f"{index}. " if is_export else f"{index}. {inst_name}."
            content.append(prefix + func_name)
            result.append(prefix + desc.format())

        return content, result


class Interface(metaclass=InterfaceMeta):
    _buffer: str
    __inst_name__: ClassVar[str] = "interface"

    def get_export_method(self) -> List[str]:
        return getattr(self, INTERFACE_EXPORT_METHOD)

    def export_to(self, context: T_Context):
        for name in self.get_export_method():
            context[name] = getattr(self, name)
        context[self.__inst_name__] = self

    @classmethod
    def get_method_description(cls) -> List[Tuple[str, str]]:
        name = cls.__inst_name__
        assert (cls is not Interface) and (
            name != Interface.__inst_name__
        ), "Interface的子类必须拥有自己的`__inst_name__`属性"

        return [
            (f"{name}.{k}", f"{name}.{v}")
            for k, v in getattr(cls, INTERFACE_METHOD_DESCRIPTION, {}).items()
        ]


class API(Interface):
    __inst_name__: ClassVar[str] = "api"

    event: Event
    context: T_Context
    bot: Bot

    def __init__(self, event: Event, bot: Bot, context: T_Context):
        super(API, self).__init__()
        self.event = event
        self.context = context
        self.bot = bot
        self.export_to(context)

    @descript(
        description="调用 OneBot V11 接口",
        parameters=dict(
            api="需要调用的接口名，参考 https://github.com/botuniverse/onebot-11/blob/master/api/public.md",
            data="以命名参数形式传入的接口调用参数",
        ),
        result=DESCRIPTION_RESULT_TYPE,
    )
    async def call_api(self, api: str, **data: object) -> Result:
        try:
            res: Dict[str, Any] = await self.bot.call_api(api, **data) or {}
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
        return Result(res)

    @export
    @descript(
        description="向QQ号为qid的用户发送私聊消息",
        parameters=dict(
            qid="需要发送私聊的QQ号",
            msg="发送的内容",
        ),
        result=DESCRIPTION_RESULT_TYPE,
    )
    async def send_prv(self, qid: int | str, msg: T_Message) -> Receipt:
        return await send_message(
            bot=self.bot,
            event=self.event,
            target=Target.user(str(qid)),
            message=msg,
        )

    @export
    @descript(
        description="向群号为gid的群聊发送消息",
        parameters=dict(
            gid="需要发送消息的群号",
            msg="发送的内容",
        ),
        result=DESCRIPTION_RESULT_TYPE,
    )
    async def send_grp(self, gid: int, msg: T_Message) -> Receipt:
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
            msg="发送的消息列表",
        ),
        result=DESCRIPTION_RESULT_TYPE,
    )
    async def send_prv_fwd(self, qid: int | str, msgs: List[T_Message]) -> None:
        await send_forward_message(
            bot=self.bot,
            event=self.event,
            target=TargetQQPrivate(user_id=int(qid)),
            msgs=msgs,
        )

    @descript(
        description="向群号为gid的群聊发送合并转发消息",
        parameters=dict(
            gid="需要发送消息的群号",
            msg="发送的消息列表",
        ),
        result=DESCRIPTION_RESULT_TYPE,
    )
    async def send_grp_fwd(self, gid: int, msgs: List[T_Message]) -> None:
        await send_forward_message(
            bot=self.bot,
            event=self.event,
            target=TargetQQGroup(group_id=int(gid)),
            msgs=msgs,
        )

    @export
    @descript(
        description="获取用户对象",
        parameters=dict(qid="用户QQ号"),
        result="User对象",
    )
    def user(self, qid: int) -> "User":
        return User(self, qid)

    @export
    @descript(
        description="获取群聊对象",
        parameters=dict(gid="群号"),
        result="Group对象",
    )
    def group(self, gid: int) -> "Group":
        return Group(self, gid)

    @export
    @descript(
        description="向当前会话发送消息",
        parameters=dict(
            msg="需要发送的消息",
        ),
        result=DESCRIPTION_RESULT_TYPE,
    )
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
    async def recall(self, msg_id: int) -> Result:
        # TODO: fix
        return await self.call_api("delete_msg", message_id=msg_id)

    @descript(
        description="判断当前会话是否为群聊",
        parameters=None,
        result="当前会话为群聊返回True，否则返回False",
    )
    def is_group(self) -> bool:
        return isinstance(extract_target(self.event, self.bot), TargetQQGroup)

    @descript(
        description="设置环境常量，在每次执行代码时加载",
        parameters=dict(
            name="设置的环境变量名",
            value="设置的环境常量，仅允许输入可被json序列化的对象，留空则为删除",
        ),
        result="无",
    )
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
    def print(self, *args, sep: str = " ", end: str = "\n", **_):
        Buffer(self.event.get_user_id()).write(sep.join(str(i) for i in args) + end)

    @export
    @descript(
        description="向当前会话发送API说明(本文档)",
        parameters=None,
        result="无",
    )
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
        parameters=dict(
            seconds="等待的时间，单位秒",
        ),
        result="无",
    )
    async def sleep(self, seconds: float) -> None:
        await asyncio.sleep(seconds)

    @export
    @descript(
        description="重置环境",
        parameters=None,
        result="无",
    )
    def reset(self) -> None:
        self.context.clear()
        self.context.update(default_context)
        self.context.update(load_const(self.event.get_user_id()))
        self.export_to(self.context)

    def export_to(self, context: T_Context) -> None:
        super(API, self).export_to(context)

        context["qid"] = int(self.event.get_user_id())
        context["usr"] = self.user(context["qid"])
        context["gid"] = getattr(self.event, "group_id", None)
        context["grp"] = self.group(context["gid"]) if context["gid"] else None

        if is_super_user(self.bot, self.event):
            module_name = __name__.rpartition(".")[0]
            module = importlib.import_module(module_name)
            context["ctx_mgr"] = getattr(module, "ctx_mgr")
            context["get_ctx"] = getattr(context["ctx_mgr"], "get_context")

    def __getattr__(self, name: str):
        return functools.partial(self.call_api, name)

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}(user_id={self.event.get_user_id()})"


class User(Interface):
    __inst_name__: ClassVar[str] = "usr"
    api: API
    uid: int

    def __init__(self, api: API, uid: int):
        super(User, self).__init__()
        self.api = api
        self.uid = uid

    @descript(
        description="向用户发送私聊消息",
        parameters=dict(msg="需要发送的消息"),
        result=DESCRIPTION_RESULT_TYPE,
    )
    async def send(self, msg: T_Message) -> Receipt:
        return await self.api.send_prv(self.uid, msg)

    @descript(
        description="向用户发送私聊合并转发消息",
        parameters=dict(msgs="需要发送的消息列表"),
        result="无",
    )
    async def send_fwd(self, msgs: List[T_Message]) -> None:
        return await self.api.send_prv_fwd(self.uid, msgs)

    def __repr__(self):
        return f"{self.__class__.__name__}(user_id={self.uid})"


class Group(Interface):
    __inst_name__: ClassVar[str] = "grp"
    api: API
    uid: int

    def __init__(self, api: API, uid: int):
        super(Group, self).__init__()
        self.api = api
        self.uid = uid

    @descript(
        description="向群聊发送消息",
        parameters=dict(msg="需要发送的消息"),
        result=DESCRIPTION_RESULT_TYPE,
    )
    async def send(self, msg: T_Message) -> Receipt:
        return await self.api.send_grp(self.uid, msg)

    @descript(
        description="向群聊发送合并转发消息",
        parameters=dict(msgs="需要发送的消息列表"),
        result="无",
    )
    async def send_fwd(self, msgs: List[T_Message]) -> None:
        return await self.api.send_grp_fwd(self.uid, msgs)

    def __repr__(self):
        return f"{self.__class__.__name__}(group_id={self.uid})"
