import abc
import dataclasses
from datetime import timedelta
from typing import Protocol, overload


@dataclasses.dataclass(frozen=True, slots=True)
class CacheStats:
    hits: int
    misses: int

    @property
    def total(self) -> int:
        return self.hits + self.misses

    @property
    def hit_ratio(self) -> float:
        return self.hits / self.total if self.total > 0 else 0.0


class BaseSerializer[T](abc.ABC):
    @abc.abstractmethod
    def dumps(self, value: T) -> bytes: ...
    @abc.abstractmethod
    def loads(self, value: bytes) -> T: ...


class BaseCache(abc.ABC):
    @abc.abstractmethod
    async def get(self, key: str) -> bytes | None: ...
    @abc.abstractmethod
    async def set(self, key: str, value: bytes, ttl: float) -> bool: ...
    @abc.abstractmethod
    async def exists(self, key: str) -> bool: ...
    @abc.abstractmethod
    async def delete(self, key: str) -> bool: ...
    @abc.abstractmethod
    async def pttl(self, key: str) -> float: ...


class Cache[T](Protocol):
    @overload
    async def get(self, key: str) -> T | None: ...
    @overload
    async def get[D](self, key: str, default: D) -> T | D: ...
    async def set(self, key: str, value: T, ttl: float | timedelta = ...) -> bool: ...
    async def exists(self, key: str) -> bool: ...
    async def delete(self, key: str) -> bool: ...
    async def pttl(self, key: str) -> float: ...
    def stats(self) -> CacheStats: ...
