import abc
import dataclasses
from collections.abc import Iterable
from datetime import timedelta
from typing import Literal, Protocol, overload


@dataclasses.dataclass(frozen=True, slots=True)
class CacheStats:
    hits: int
    misses: int
    total: int
    hit_ratio: float

    @classmethod
    def of(cls, hits: int, misses: int) -> CacheStats:
        total = hits + misses
        hit_ratio = hits / total if total > 0 else 0.0
        return cls(hits, misses, total, hit_ratio)


class BaseSerializer[T](abc.ABC):
    @abc.abstractmethod
    def dumps(self, value: T) -> bytes: ...
    @abc.abstractmethod
    def loads(self, value: bytes) -> T: ...


# -2: key does not exist
# -1: key exists but has no expiration
# non-negative float: remaining ttl in seconds
type PTTL = Literal[-2, -1] | float


class BaseCacheBackend(abc.ABC):
    @abc.abstractmethod
    async def get(self, key: str) -> bytes | None: ...
    @abc.abstractmethod
    async def multi_get(self, keys: Iterable[str]) -> list[bytes | None]: ...
    @abc.abstractmethod
    async def set(self, key: str, value: bytes, ttl: float | None) -> bool: ...
    @abc.abstractmethod
    async def multi_set(self, mapping: dict[str, bytes], ttl: float | None) -> int: ...
    @abc.abstractmethod
    async def exists(self, key: str) -> bool: ...
    @abc.abstractmethod
    async def delete(self, key: str) -> bool: ...
    @abc.abstractmethod
    async def pttl(self, key: str) -> PTTL: ...


class Cache[T](Protocol):
    @overload
    async def get(self, key: str) -> T | None: ...
    @overload
    async def get[D](self, key: str, default: D) -> T | D: ...
    async def multi_get(self, keys: Iterable[str]) -> list[bytes | None]: ...
    async def set(
        self, key: str, value: T, ttl: float | timedelta | None = ...
    ) -> bool: ...
    async def multi_set(self, mapping: dict[str, bytes], ttl: float | None) -> int: ...
    async def exists(self, key: str) -> bool: ...
    async def delete(self, key: str) -> bool: ...
    async def pttl(self, key: str) -> PTTL: ...
    def stats(self) -> CacheStats: ...
