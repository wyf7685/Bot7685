from pathlib import Path
from typing import Any, Callable, Union

from nonebot.adapters import Message, MessageSegment
from nonebot_plugin_alconna.uniseg import Segment as UniSegment
from nonebot_plugin_alconna.uniseg import UniMessage

# description
DESCRIPTION_FORMAT = "{decl}\n* 描述: {desc}\n* 参数:\n{params}\n* 返回值:\n  {res}\n"
DESCRIPTION_RESULT_TYPE = "Result类对象，可通过属性名获取接口响应"

# interface
INTERFACE_METHOD_DESCRIPTION = "__method_description__"
INTERFACE_EXPORT_METHOD = "__export_method__"
INTERFACE_INST_NAME = "__inst_name__"


DATA_PATH = Path() / "data" / "exe_code"
DATA_PATH.mkdir(parents=True, exist_ok=True)

T_Message = Union[str, Message, MessageSegment, UniMessage, UniSegment]
T_Context = dict[str, Any]
T_API_Result = Union[dict[str, Any], list[Any]]
T_ResultCallback = Callable[[Any], Any]
T_ConstVar = Union[str, bool, int, float, dict[str, "T_ConstVar"], list["T_ConstVar"]]
