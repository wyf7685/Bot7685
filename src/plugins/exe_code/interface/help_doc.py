import inspect
from dataclasses import dataclass
from typing import Any, Callable, Optional, ParamSpec, TypeVar

from nonebot_plugin_alconna.uniseg import Receipt

from ..constant import (
    DESCRIPTION_FORMAT,
    DESCRIPTION_RECEIPT_TYPE,
    DESCRIPTION_RESULT_TYPE,
    INTERFACE_METHOD_DESCRIPTION,
    T_Message,
)
from .utils import Result

P = ParamSpec("P")
R = TypeVar("R")
EMPTY = inspect.Signature.empty


type_alias: dict[type, str] = {
    Receipt: "Receipt",
    Result: "Result",
    T_Message: "T_Message",
    EMPTY: "Unkown",  # not supposed to appear in docs
}


def _type_string(t: type | str) -> str:
    if isinstance(t, str):
        return t
    elif t in type_alias:
        return type_alias[t]
    return inspect.formatannotation(t)


def func_declaration(func: Callable[..., Any]) -> str:
    sig = inspect.Signature.from_callable(func)
    params = [
        f"{name}: {_type_string(param.annotation)}"
        for name, param in sig.parameters.items()
        if name != "self"
    ]
    result = _type_string(sig.return_annotation)

    return f"{func.__name__}({', '.join(params)}) -> {result}"


@dataclass
class FuncDescription:
    description: str
    parameters: Optional[dict[str, str]]
    result: Optional[str]

    def format(self, func: Callable[..., Any]):
        return DESCRIPTION_FORMAT.format(
            decl=func_declaration(func),
            desc=self.description,
            params=(
                "\n".join(f" - {k}: {v}" for k, v in self.parameters.items())
                if self.parameters
                else "无"
            ),
            res=self.result or "无",
        )


def descript(
    description: str,
    parameters: Optional[dict[str, str]],
    result: Optional[str] = None,
    *,
    ignore: Optional[list[str]] = None,
):
    def decorator(call: Callable[P, R]) -> Callable[P, R]:
        nonlocal result

        sig = inspect.Signature.from_callable(call)
        if parameters is not None:
            for name, param in sig.parameters.items():
                if name == "self" or (ignore is not None and name in ignore):
                    continue
                text = f"方法 '{call.__name__}' 的参数 '{name}'"
                assert param.annotation is not EMPTY, f"{text} 未添加类型注释注释"
                assert name in parameters, f"{text} 未添加描述"

        if result is None:
            if sig.return_annotation is Result:
                result = DESCRIPTION_RESULT_TYPE
            elif sig.return_annotation is Receipt:
                result = DESCRIPTION_RECEIPT_TYPE
            else:
                assert (
                    sig.return_annotation is None
                ), f"方法 '{call.__name__}' 的返回值未添加类型注释注释"

        setattr(
            call,
            INTERFACE_METHOD_DESCRIPTION,
            FuncDescription(description, parameters, result),
        )
        return call

    return decorator
