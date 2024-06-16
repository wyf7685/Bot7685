from typing import Any, Callable, Union

from nonebot.adapters import Message, MessageSegment
from nonebot_plugin_alconna.uniseg import Segment as UniSegment
from nonebot_plugin_alconna.uniseg import UniMessage
from nonebot_plugin_datastore import get_plugin_data

DATA_PATH = get_plugin_data().data_dir

# description
DESCRIPTION_FORMAT = "{decl}\n* 描述: {desc}\n* 参数:\n{params}\n* 返回值:\n  {res}\n"
DESCRIPTION_RESULT_TYPE = "Result类对象，可通过属性名获取接口响应"

# interface
INTERFACE_METHOD_DESCRIPTION = "__method_description__"
INTERFACE_EXPORT_METHOD = "__export_method__"
INTERFACE_INST_NAME = "__inst_name__"


T_Message = Union[str, Message, MessageSegment, UniMessage, UniSegment]
T_Context = dict[str, Any]
T_API_Result = Union[dict[str, Any], list[Any]]
T_ResultCallback = Callable[[Any], Any]
T_ConstVar = Union[str, bool, int, float, dict[str, "T_ConstVar"], list["T_ConstVar"]]
