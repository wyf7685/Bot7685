import json
from pathlib import Path
from typing import Optional, TypeVar

from nonebot_plugin_alconna.uniseg import At, Image, Reply, Text, UniMessage

from ..constant import DATA_PATH, T_ConstVar, T_Context

T = TypeVar("T")
default_context: T_Context = {}


def context_var(item: T, name: Optional[str] = None) -> T:
    key = name or getattr(item, "__name__", None)
    assert key is not None, f"Name for {item!r} cannot be empty"
    default_context[key] = item
    return item


context_var((None, None), "__exception__")
context_var(lambda x: At(flag="user", target=str(x)), "At")
context_var(lambda x: Reply(id=str(x)), "Reply")
[context_var(i) for i in {Image, Text, UniMessage}]


def _const_var_path(uin: str) -> Path:
    fp = DATA_PATH() / f"{uin}.json"
    if not fp.exists():
        fp.parent.mkdir(parents=True, exist_ok=True)
        fp.write_text("{}")
    return fp


def set_const(uin: str, name: str, value: Optional[T_ConstVar] = None):
    fp = _const_var_path(uin)
    data = json.loads(fp.read_text())
    if value is not None:
        data[name] = value
    elif name in data:
        del data[name]
    fp.write_text(json.dumps(data))


def load_const(uin: str) -> dict[str, T_ConstVar]:
    return json.loads(_const_var_path(uin).read_text())
