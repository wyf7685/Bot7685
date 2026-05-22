# ruff: noqa: A002

from collections.abc import Mapping, Sequence
from typing import TYPE_CHECKING, Literal, overload

from loguru import logger
from nonebot.utils import escape_tag
from pydantic import BaseModel

from .abstract import Cache
from .impl import CacheAdapter, get_cache_backend, get_serializer

if TYPE_CHECKING:
    from _typeshed import DataclassInstance

    type JsonSerializable = (
        str
        | int
        | float
        | bool
        | None
        | Sequence["JsonSerializable"]
        | Mapping[str, "JsonSerializable"]
    )
    type Serializable = (
        str
        | bytes
        | int
        | float
        | bool
        | None
        | Sequence[Serializable]
        | Mapping[str, Serializable]
        | Mapping[int, Serializable]
        | set[Serializable]
        | DataclassInstance
        | BaseModel
    )

    @overload
    def get_cache[T: JsonSerializable](
        namespace: str,
        type: type[T],
        /,
        *,
        mode: Literal["json"],
    ) -> Cache[T]: ...
    @overload
    def get_cache[T: Serializable](
        namespace: str,
        type: type[T],
        /,
    ) -> Cache[T]: ...
    @overload
    def get_cache[T](
        namespace: str,
        type: type[T],
        /,
        *,
        mode: Literal["pickle"],
    ) -> Cache[T]: ...


def get_cache[T](
    namespace: str,
    type: type[T],
    /,
    *,
    mode: Literal["json", "pickle"] | None = None,
) -> Cache[T]:
    logger.opt(colors=True).debug(
        f"Initializing cache for namespace '<y>{escape_tag(namespace)}</>' "
        f"with type <g>{escape_tag(repr(type))}</> (mode=<c>{mode}</>)"
    )
    backend = get_cache_backend()
    serializer = get_serializer(type, mode)
    return CacheAdapter(backend, namespace, serializer)
