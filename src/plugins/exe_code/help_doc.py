import inspect
from dataclasses import dataclass
from typing import Any, Callable, Dict, Optional, ParamSpec, Type, TypeVar

from .const import DESCRIPTION_MODEL, INTERFACE_METHOD_DESCRIPTION, T_Message

P = ParamSpec("P")
R = TypeVar("R")
type_alia: Dict[Type[type], str] = {}


@dataclass
class FuncDescription:
    declaration: str
    description: str
    parameters: Optional[Dict[str, str]]
    result: str

    def format(self):
        return DESCRIPTION_MODEL.format(
            decl=self.declaration,
            desc=self.description,
            params=(
                "\n".join(f" - {k}: {v}" for k, v in self.parameters.items())
                if self.parameters
                else "无"
            ),
            res=self.result,
        )


def set_type_alia(t: Any, alia: str):
    type_alia[t] = alia


set_type_alia(T_Message, "T_Message")


def _type_string(t: Type[type] | str) -> str:
    if isinstance(t, str):
        return t
    elif t in type_alia:
        return type_alia[t]
    return inspect.formatannotation(t)


def func_declaration(func: Callable) -> str:
    code = func.__code__
    args = list(code.co_varnames)[: code.co_argcount]
    if "self" in args:
        args.remove("self")
    anno = func.__annotations__

    for i in range(len(args)):
        if args[i] in anno:
            args[i] += f": {_type_string(anno[args[i]])}"

    ret = _type_string(anno.get("return", "Unkown"))
    return f"{func.__name__}({', '.join(args)}) -> {ret}"


def descript(description: str, parameters: Optional[Dict[str, str]], result: str):
    def decorator(func: Callable[P, R]) -> Callable[P, R]:
        setattr(
            func,
            INTERFACE_METHOD_DESCRIPTION,
            FuncDescription(
                func_declaration(func),
                description,
                parameters,
                result,
            ),
        )
        return func

    return decorator
