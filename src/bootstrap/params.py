import inspect
from collections.abc import AsyncGenerator, Awaitable, Callable, Generator
from contextlib import AsyncExitStack, asynccontextmanager, contextmanager
from typing import Any, Optional, Self, cast, overload, override

from nonebot.dependencies import Param
from nonebot.internal.params import DependencyCache
from nonebot.typing import _DependentCallable as DependentCallable
from nonebot.utils import (
    generic_check_issubclass,
    is_async_gen_callable,
    is_coroutine_callable,
    is_gen_callable,
    run_sync,
    run_sync_ctx_manager,
)
from tarina.generic import is_optional

T_DependencyCache = dict[DependentCallable[Any], DependencyCache]


class StackParam(Param):
    def __repr__(self) -> str:
        return "bot7685.StackParam()"

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
        return "bot7685.DependencyCacheParam()"

    @classmethod
    @override
    def _check_param(
        cls, param: inspect.Parameter, allow_types: tuple[type[Param], ...]
    ) -> Self | None:
        if param.annotation == dict[DependentCallable[Any], DependencyCache]:
            return cls(..., type=dict[DependentCallable[Any], DependencyCache])
        if param.annotation == dict[DependentCallable[Any], DependencyCache] | None:
            return cls(None, type=dict[DependentCallable[Any], DependencyCache])
        if param.annotation == Optional[dict[DependentCallable[Any], DependencyCache]]:  # noqa: UP045
            return cls(None, type=dict[DependentCallable[Any], DependencyCache])
        if is_optional(param.annotation, dict[DependentCallable[Any], DependencyCache]):
            return cls(None, type=dict[DependentCallable[Any], DependencyCache])
        return None

    @override
    async def _solve(
        self,
        dependency_cache: dict[DependentCallable[Any], DependencyCache] | None = None,
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


@overload
async def call_as_dependent[**P, T](
    call: Callable[P, Awaitable[T]],
    stack: AsyncExitStack | None = None,
    dependency_cache: T_DependencyCache | None = None,
    /,
    *args: P.args,
    **kwargs: P.kwargs,
) -> T: ...
@overload
async def call_as_dependent[**P, T](
    call: Callable[P, T],
    stack: AsyncExitStack | None = None,
    dependency_cache: T_DependencyCache | None = None,
    /,
    *args: P.args,
    **kwargs: P.kwargs,
) -> T: ...


async def call_as_dependent[**P, T](
    call: Callable[P, Awaitable[T]] | Callable[P, T],
    stack: AsyncExitStack | None = None,
    dependency_cache: T_DependencyCache | None = None,
    /,
    *args: P.args,
    **kwargs: P.kwargs,
) -> T:
    dependency_cache = dependency_cache or {}
    if call in dependency_cache:
        return await dependency_cache[call].wait()

    if is_gen_callable(call) or is_async_gen_callable(call):
        assert isinstance(stack, AsyncExitStack), (
            "Generator dependency should be called in context"
        )
        if is_gen_callable(call):
            sync_cm = contextmanager(cast("Callable[P, Generator[T]]", call))(
                *args, **kwargs
            )
            cm = run_sync_ctx_manager(sync_cm)
        else:
            cm = asynccontextmanager(cast("Callable[P, AsyncGenerator[T]]", call))(
                *args, **kwargs
            )

        target = stack.enter_async_context(cm)
    elif is_coroutine_callable(call):
        target = call(*args, **kwargs)
    else:
        target = run_sync(call)(*args, **kwargs)

    cache = dependency_cache[call] = DependencyCache()
    try:
        result = await cast("Awaitable[T]", target)
    except Exception as e:
        cache.set_exception(e)
        raise
    except BaseException as e:
        cache.set_exception(e)
        dependency_cache.pop(call, None)
        raise
    cache.set_result(result)
    return result
