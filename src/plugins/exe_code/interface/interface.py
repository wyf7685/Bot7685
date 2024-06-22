from typing import Any, Callable, ClassVar, NamedTuple, cast

from ..constant import INTERFACE_INST_NAME, INTERFACE_METHOD_DESCRIPTION, T_Context
from .help_doc import FuncDescription
from .utils import is_export_method


class _Desc(NamedTuple):
    inst_name: str
    func_name: str
    is_export: bool
    description: str


class InterfaceMeta(type):
    __interface_map__: ClassVar[dict[str, "InterfaceMeta"]] = {}

    __export_method__: list[str]
    __method_description__: dict[str, FuncDescription]

    def __new__(cls, name: str, bases: tuple, attrs: dict[str, object]):
        if name in cls.__interface_map__:
            raise TypeError(f"Interface {name} already exists")

        Interface = super(InterfaceMeta, cls).__new__(cls, name, bases, attrs)
        attr = Interface.__dict__  # shortcut

        # export
        Interface.__export_method__ = [
            name for name, value in attr.items() if is_export_method(value)
        ]

        # description
        Interface.__method_description__ = {
            name: desc
            for name, value in attr.items()
            if (desc := getattr(value, INTERFACE_METHOD_DESCRIPTION, None))
        }

        # inst_name
        if INTERFACE_INST_NAME not in attr:
            setattr(Interface, INTERFACE_INST_NAME, name.lower())

        # store interface class
        cls.__interface_map__[name] = Interface
        return Interface

    def get_export_method(self) -> list[str]:
        return self.__export_method__

    def __get_method_description(self) -> list[_Desc]:
        methods: list[_Desc] = []
        inst_name: str = getattr(self, "__inst_name__")
        for func_name, desc in self.__method_description__.items():
            func = cast(Callable[..., Any], getattr(self, func_name))
            is_export = is_export_method(func)
            methods.append(_Desc(inst_name, func_name, is_export, desc.format(func)))
        return methods

    @classmethod
    def get_all_description(cls) -> tuple[list[str], list[str]]:
        methods: list[_Desc] = []
        for cls_obj in cls.__interface_map__.values():
            methods.extend(cls_obj.__get_method_description())
        methods.sort(key=lambda x: (not x.is_export, x.inst_name, x.func_name))

        content: list[str] = []
        result: list[str] = []
        for index, desc in enumerate(methods, 1):
            prefix = f"{index}. "
            if not desc.is_export:
                prefix += f"{desc.inst_name}."
            content.append(prefix + desc.func_name)
            result.append(prefix + desc.description)

        return content, result


class Interface(metaclass=InterfaceMeta):
    __inst_name__: ClassVar[str] = "interface"
    __export_method__: ClassVar[list[str]]
    __method_description__: ClassVar[dict[str, str]]

    def export_to(self, context: T_Context):
        for name in type(self).get_export_method():
            context[name] = getattr(self, name)
        context[self.__inst_name__] = self
