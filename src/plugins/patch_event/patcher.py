import functools
import inspect
from collections.abc import Callable
from typing import Protocol, cast

import nonebot
from nonebot.adapters import Event


class PatcherHandle[T: Event](Protocol):
    __call__: Callable[[T], str]
    original: Callable[[T], str]

    def patch(self) -> None: ...
    def restore(self) -> None: ...


logger = nonebot.logger.opt(colors=True)
_PATCHERS: set[PatcherHandle] = set()


@nonebot.get_driver().on_startup
async def _() -> None:
    for patcher in _PATCHERS:
        patcher.patch()


def patcher[T: Event](call: Callable[[T], str]) -> PatcherHandle[T]:
    cls: type[T] = inspect.get_annotations(call)["self"]
    assert issubclass(cls, Event)
    original = cls.get_log_string
    module_name = cls.__module__.replace("nonebot.adapters.", "~")
    colored = f"<m>{module_name}</m>.<g>{cls.__name__}</g>.<y>get_log_string</y>"

    @functools.wraps(original)
    def wrapper(self: T) -> str:
        return call(self)

    def patch() -> None:
        cls.get_log_string = wrapper
        logger.debug(f"Patch {colored}")

    def restore() -> None:
        cls.get_log_string = original
        logger.debug(f"Restore {colored}")

    handle = cast("PatcherHandle[T]", call)
    handle.original = original
    handle.patch = patch
    handle.restore = restore
    _PATCHERS.add(handle)
    return handle
