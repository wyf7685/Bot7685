import json
import pickle
from collections.abc import Callable
from typing import Any, Literal, override

from pydantic import TypeAdapter

from ..abstract import BaseSerializer
from ..config import cache_config

_serializers: dict[type | str, type[BaseSerializer[Any]]] = {}


def _register_serializer[T, S: BaseSerializer = BaseSerializer[T]](
    key: type[T] | str, /
) -> Callable[[type[S]], type[S]]:
    def decorator(serializer_cls: type[S]) -> type[S]:
        _serializers[key] = serializer_cls
        return serializer_cls

    return decorator


def get_serializer[T](
    type: type[T],  # noqa: A002
    mode: Literal["json", "pickle"] | None,
) -> BaseSerializer[T]:
    if mode is not None:
        return _serializers[mode]()
    if type in _serializers:
        return _serializers[type]()
    return PydanticSerializer(type)


@_register_serializer(bytes)
class BytesSerializer(BaseSerializer[bytes]):
    @override
    def dumps(self, value: bytes) -> bytes:
        return value

    @override
    def loads(self, value: bytes) -> bytes:
        return value


@_register_serializer(str)
class StringSerializer(BaseSerializer[str]):
    @override
    def dumps(self, value: str) -> bytes:
        return value.encode("utf-8")

    @override
    def loads(self, value: bytes) -> str:
        return value.decode("utf-8")


@_register_serializer(bool)
class BoolSerializer(BaseSerializer[bool]):
    @override
    def dumps(self, value: bool) -> bytes:
        return b"1" if value else b"0"

    @override
    def loads(self, value: bytes) -> bool:
        return value == b"1"


@_register_serializer("pickle")
class PickleSerializer[T](BaseSerializer[T]):
    def __init__(self) -> None:
        self.protocol = cache_config.cache_pickle_protocol

    @override
    def dumps(self, value: T) -> bytes:
        return pickle.dumps(value, protocol=self.protocol)

    @override
    def loads(self, value: bytes) -> T:
        return pickle.loads(value)  # noqa: S301


@_register_serializer("json")
class JsonSerializer[T](BaseSerializer[T]):
    @override
    def dumps(self, value: T) -> bytes:
        return json.dumps(
            value,
            ensure_ascii=False,
            separators=(",", ":"),
        ).encode("utf-8")

    @override
    def loads(self, value: bytes) -> T:
        return json.loads(value.decode("utf-8"))


class PydanticSerializer[T](BaseSerializer[T]):
    def __init__(self, type: type[T]) -> None:  # noqa: A002
        self._type = type
        self._adapter = TypeAdapter(type)

    @override
    def dumps(self, value: T) -> bytes:
        return self._adapter.dump_json(value)

    @override
    def loads(self, value: bytes) -> T:
        return self._adapter.validate_json(value)
