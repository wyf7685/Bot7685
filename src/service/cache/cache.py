# ruff: noqa: A002

from collections.abc import Sequence
from typing import TYPE_CHECKING, Literal, overload

from loguru import logger
from nonebot.utils import escape_tag
from pydantic import BaseModel

from .abstract import Cache
from .impl import CacheAdapter, get_cache_impl, get_serializer

if TYPE_CHECKING:
    from _typeshed import DataclassInstance


type _Serializable = (
    str
    | bytes
    | int
    | float
    | bool
    | None
    | Sequence[_Serializable]
    | dict[str, _Serializable]
    | dict[int, _Serializable]
    | tuple[_Serializable, ...]
    | set[_Serializable]
    | DataclassInstance
    | BaseModel
)


@overload
def get_cache[T: _Serializable](
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
    pickle: Literal[True],
) -> Cache[T]: ...


def get_cache[T](
    namespace: str,
    type: type[T],
    /,
    *,
    pickle: bool = False,
) -> Cache[T]:
    logger.opt(colors=True).debug(
        f"Initializing cache for namespace '<y>{escape_tag(namespace)}</>' "
        f"with type <g>{escape_tag(repr(type))}</> (pickle=<c>{pickle}</>)"
    )
    impl = get_cache_impl()
    serializer = get_serializer(type, pickle)
    return CacheAdapter(impl, namespace, serializer)
