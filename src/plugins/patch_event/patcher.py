import inspect
from collections.abc import Callable
from typing import Protocol, cast

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


def patcher[T: Event](call: PatcherCall[T]) -> PatcherHandle[T]:
    cls: type[T] = inspect.get_annotations(call)["self"]
    assert issubclass(cls, Event)
    original = cls.get_log_string
    bases = cls.__bases__
    patched = (type("Patcher", bases, {"get_log_string": call}),)
    module_name = cls.__module__.replace("nonebot.adapters.", "~")

    def patch() -> None:
        cls.__bases__ = patched
        logger.debug(f"Patch <m>{module_name}</m>.<g>{cls.__name__}</g>")

    def restore() -> None:
        cls.__bases__ = bases
        logger.debug(f"Restore <m>{module_name}</m>.<g>{cls.__name__}</g>")

    handle = cast("PatcherHandle[T]", call)
    handle.original = original
    handle.patch = patch
    handle.restore = restore
    _PATCHERS.add(handle)
    return handle


@nonebot.get_driver().on_startup
def setup() -> None:
    for patcher in _PATCHERS:
        patcher.patch()


@nonebot.get_driver().on_shutdown
def dispose() -> None:
    for patcher in _PATCHERS:
        patcher.restore()
