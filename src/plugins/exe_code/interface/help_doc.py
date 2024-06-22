import inspect
from dataclasses import dataclass
from typing import Any, Callable, Optional, ParamSpec, TypeVar

from ..constant import DESCRIPTION_FORMAT, INTERFACE_METHOD_DESCRIPTION, T_Message
from .utils import Receipt, Result

P = ParamSpec("P")
R = TypeVar("R")

type_alias: dict[type, str] = {
    Receipt: "Receipt",
    Result: "Result",
    T_Message: "T_Message",
    inspect.Signature.empty: "Unkown",
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
    result: Optional[str],
):
    def decorator(func: Callable[P, R]) -> Callable[P, R]:
        setattr(
            func,
            INTERFACE_METHOD_DESCRIPTION,
            FuncDescription(description, parameters, result),
        )
        return func

    return decorator
