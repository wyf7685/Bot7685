from pathlib import Path
from typing import Any, Callable, Dict, List, Union

from nonebot.adapters import Message, MessageSegment
from nonebot_plugin_alconna.uniseg import Segment as UniSegment
from nonebot_plugin_alconna.uniseg import UniMessage

# context
CONTEXT_PY_PRINT_NAME = "py_print"

# description
DESCRIPTION_MODEL = "{decl}\n* 描述: {desc}\n* 参数:\n{params}\n* 返回值:\n  {res}\n"
DESCRIPTION_PROPERTY_MODEL = ("{decl}\n* 描述: {desc}",)
DESCRIPTION_RESULT_TYPE = "Result类对象，可通过属性名获取接口响应"

# interface
INTERFACE_METHOD_DESCRIPTION = "__method_description__"
INTERFACE_EXPORT_METHOD = "__export_method__"
INTERFACE_INST_NAME = "__inst_name__"


DATA_PATH = Path() / "data" / "exe_code"
DATA_PATH.mkdir(parents=True, exist_ok=True)

T_Message = Union[str, Message, MessageSegment, UniMessage, UniSegment]
T_Context = Dict[str, Any]
T_API_Result = Union[Dict[str, Any], List[Any]]
T_ResultCallback = Callable[[Any], Any]
T_ConstVar = Union[str, bool, int, float]
