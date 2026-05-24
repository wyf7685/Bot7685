import inspect
from collections.abc import Awaitable
from contextlib import AsyncExitStack
from typing import Any, Optional, Self, override

from nonebot.dependencies import Param
from nonebot.internal.params import DependencyCache
from nonebot.typing import _DependentCallable
from nonebot.utils import generic_check_issubclass
from tarina.generic import is_optional

T_DependencyCache = dict[_DependentCallable[Any], DependencyCache]


class StackParam(Param):
    def __repr__(self) -> str:
        return "_StackParam()"

    @classmethod
    @override
    def _check_param(
        cls, param: inspect.Parameter, allow_types: tuple[type[Param], ...]
    ) -> Self | None:
        if param.annotation == AsyncExitStack:
            return cls(..., type=AsyncExitStack)
        if param.annotation == AsyncExitStack | None:
            return cls(None, type=AsyncExitStack)
        if param.annotation == Optional[AsyncExitStack]:  # noqa: UP045
            return cls(None, type=AsyncExitStack)
        if generic_check_issubclass(param.annotation, AsyncExitStack):
            return cls(None, type=AsyncExitStack)
        return None

    @override
    async def _solve(self, stack: AsyncExitStack | None = None, **kwargs: Any) -> Any:
        return stack


class DependencyCacheParam(Param):
    def __repr__(self) -> str:
        return "_DependencyCacheParam()"

    @classmethod
    @override
    def _check_param(
        cls, param: inspect.Parameter, allow_types: tuple[type[Param], ...]
    ) -> Self | None:
        if param.annotation == dict[_DependentCallable[Any], DependencyCache]:
            return cls(..., type=dict[_DependentCallable[Any], DependencyCache])
        if param.annotation == dict[_DependentCallable[Any], DependencyCache] | None:
            return cls(None, type=dict[_DependentCallable[Any], DependencyCache])
        if param.annotation == Optional[dict[_DependentCallable[Any], DependencyCache]]:  # noqa: UP045
            return cls(None, type=dict[_DependentCallable[Any], DependencyCache])
        if is_optional(
            param.annotation, dict[_DependentCallable[Any], DependencyCache]
        ):
            return cls(None, type=dict[_DependentCallable[Any], DependencyCache])
        return None

    @override
    async def _solve(
        self,
        dependency_cache: dict[_DependentCallable[Any], DependencyCache] | None = None,
        **kwargs: Any,
    ) -> Any:
        return dependency_cache


def patch_pcs_params() -> None:
    import nonebot.message as mod

    for name in ("EVENT_PCS_PARAMS", "RUN_PREPCS_PARAMS", "RUN_POSTPCS_PARAMS"):
        params: list[type[Param]] = list(getattr(mod, name))
        if StackParam not in params:
            params = [*params[:-1], StackParam, params[-1]]
        if DependencyCacheParam not in params:
            params = [*params[:-1], DependencyCacheParam, params[-1]]
        setattr(mod, name, tuple(params))


async def call_coro_as_dependent[T](
    call: _DependentCallable[T],
    coro: Awaitable[T],
    dependency_cache: T_DependencyCache | None = None,
) -> T:
    dependency_cache = dependency_cache or {}
    if call in dependency_cache:
        cache = dependency_cache[call]
        return await cache.wait()

    cache = dependency_cache[call] = DependencyCache()
    try:
        result = await coro
    except Exception as e:
        cache.set_exception(e)
        raise
    except BaseException as e:
        cache.set_exception(e)
        dependency_cache.pop(call, None)
        raise
    cache.set_result(result)
    return result
