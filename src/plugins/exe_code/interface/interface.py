from typing import ClassVar, Tuple

from ..const import INTERFACE_INST_NAME, INTERFACE_METHOD_DESCRIPTION, T_Context
from ..help_doc import FuncDescription
from .utils import is_export_method


class InterfaceMeta(type):
    __interface_map__: ClassVar[dict[str, "InterfaceMeta"]] = {}

    __export_method__: list[str]
    __method_description__: dict[str, str]

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

    @classmethod
    def get_all_description(cls) -> Tuple[list[str], list[str]]:
        content: list[str] = []
        result: list[str] = []

        # (is_export, inst_name, func_name, desc)
        methods: list[Tuple[bool, str, str, FuncDescription]] = []
        for _, cls_obj in cls.__interface_map__.items():
            inst_name: str = getattr(cls_obj, INTERFACE_INST_NAME)
            description: dict[str, FuncDescription] = getattr(
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
    __inst_name__: ClassVar[str] = "interface"
    __export_method__: ClassVar[list[str]]
    __method_description__: ClassVar[dict[str, str]]

    @classmethod
    def get_export_method(cls) -> list[str]:
        return cls.__export_method__

    def export_to(self, context: T_Context):
        for name in self.get_export_method():
            context[name] = getattr(self, name)
        context[self.__inst_name__] = self

    @classmethod
    def get_method_description(cls) -> list[Tuple[str, str]]:
        name = cls.__inst_name__
        assert (cls is not Interface) and (
            name != Interface.__inst_name__
        ), "Interface的子类必须拥有自己的`__inst_name__`属性"

        return [
            (f"{name}.{k}", f"{name}.{v}")
            for k, v in cls.__method_description__.items()
        ]
