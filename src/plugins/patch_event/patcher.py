import inspect
from collections.abc import Callable
from typing import TYPE_CHECKING, Protocol, cast

import nonebot
from nonebot.adapters import Event

type PatcherCall[T: Event] = Callable[[T], str]


class PatcherHandle[T: Event](Protocol):
    __call__: PatcherCall[T]
    original: PatcherCall[T]

    def patch(self) -> None: ...
    def restore(self) -> None: ...


logger = nonebot.logger.opt(colors=True)
_PATCHERS: set[PatcherHandle] = set()


@nonebot.get_driver().on_startup
async def _() -> None:
    for patcher in _PATCHERS:
        patcher.patch()


def patcher[T: Event](call: PatcherCall[T]) -> PatcherHandle[T]:
    cls: type[T] = inspect.get_annotations(call)["self"]
    assert issubclass(cls, Event)
    original = cls.get_log_string
    if TYPE_CHECKING:
        call = original  # copy signature(?)

    module_name = cls.__module__.replace("nonebot.adapters.", "~")
    colored = f"<m>{module_name}</m>.<g>{cls.__name__}</g>.<y>get_log_string</y>"

    def patch() -> None:
        cls.get_log_string = call
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


@nonebot.get_driver().on_shutdown
def dispose() -> None:
    for patcher in _PATCHERS:
        patcher.restore()
