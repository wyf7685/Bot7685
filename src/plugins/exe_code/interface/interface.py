from typing import Any, Callable, ClassVar, Tuple, cast

from ..constant import INTERFACE_INST_NAME, INTERFACE_METHOD_DESCRIPTION, T_Context
from .help_doc import FuncDescription
from .utils import is_export_method


class InterfaceMeta(type):
    __interface_map__: ClassVar[dict[str, "InterfaceMeta"]] = {}

    __export_method__: list[str]
    __method_description__: dict[str, FuncDescription]

    def __new__(cls, name: str, bases: tuple, attrs: dict[str, object]):
        if name in cls.__interface_map__:
            raise TypeError(f"Interface {name} already exists")

        interface_cls = super(InterfaceMeta, cls).__new__(cls, name, bases, attrs)
        attr = interface_cls.__dict__

        # export
        interface_cls.__export_method__ = [
            k for k, v in attr.items() if is_export_method(v)
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

    def get_export_method(self) -> list[str]:
        return self.__export_method__

    def __get_method_description(self) -> list[Tuple[bool, str, str]]:
        # (is_export, func_name, desc)
        methods: list[Tuple[bool, str, str]] = []
        description: dict[str, FuncDescription] = self.__method_description__
        for func_name, desc in description.items():
            func = cast(Callable[..., Any], getattr(self, func_name))
            is_export = is_export_method(func)
            methods.append((is_export, func_name, desc.format(func)))
        return methods

    @classmethod
    def get_all_description(cls) -> Tuple[list[str], list[str]]:
        # (is_export, func_name, desc, inst_name)
        methods: list[Tuple[bool, str, str, str]] = []
        for _, cls_obj in cls.__interface_map__.items():
            methods.extend(
                (*item, getattr(cls_obj, "__inst_name__", ""))
                for item in cls_obj.__get_method_description()
            )
        methods.sort(key=lambda x: (1 - x[0], x[3], x[1]))

        content: list[str] = []
        result: list[str] = []
        for index, (is_export, func_name, desc, inst_name) in enumerate(methods, 1):
            prefix = f"{index}. "
            if is_export:
                prefix += f"{inst_name}."
            content.append(prefix + func_name)
            result.append(prefix + desc)

        return content, result


class Interface(metaclass=InterfaceMeta):
    __inst_name__: ClassVar[str] = "interface"
    __export_method__: ClassVar[list[str]]
    __method_description__: ClassVar[dict[str, str]]

    def export_to(self, context: T_Context):
        for name in type(self).get_export_method():
            context[name] = getattr(self, name)
        context[self.__inst_name__] = self
