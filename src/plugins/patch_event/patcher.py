import functools
import inspect
from collections.abc import Callable
from typing import Protocol, cast

import nonebot
from nonebot.adapters import Event

from .config import plugin_config
from .highlight import Highlight

type PatcherCall[T: Event] = Callable[[T], str]


class PatcherHandle[T: Event](Protocol):
    __call__: PatcherCall[T]
    original: PatcherCall[T]

    def patch(self) -> None: ...
    def restore(self) -> None: ...


logger = nonebot.logger.opt(colors=True)
_PATCHERS: set[PatcherHandle] = set()


def copy_signature[C: Callable](source: C, target: Callable[..., object], /) -> C:
    return cast("C", functools.update_wrapper(target, source))


def apply_debug_wrapper[T: Event](call: PatcherCall[T]) -> PatcherCall[T]:
    if not plugin_config.patch_event_debug:
        return call

    @functools.wraps(call)
    def wrapper(self: T) -> str:
        logger.debug(Highlight.apply(self))
        return call(self)

    return wrapper


def patcher[T: Event](call: PatcherCall[T]) -> PatcherHandle[T]:
    cls: type[T] = inspect.get_annotations(call)["self"]
    assert issubclass(cls, Event)
    original = cls.get_log_string
    wrapper = copy_signature(original, apply_debug_wrapper(call))
    module_name = cls.__module__.replace("nonebot.adapters.", "~")

    def patch() -> None:
        cls.get_log_string = wrapper
        logger.debug(f"Patch <m>{module_name}</m>.<g>{cls.__name__}</g>")

    def restore() -> None:
        cls.get_log_string = original
        logger.debug(f"Restore <m>{module_name}</m>.<g>{cls.__name__}</g>")

    handle = cast("PatcherHandle[T]", call)
    handle.original = original
    handle.patch = patch
    handle.restore = restore
    _PATCHERS.add(handle)
    return handle


@patcher
def patch_base_event(self: Event) -> str:
    return f"[{Highlight.event_type(self.get_event_name())}]: {Highlight.apply(self)}"


@nonebot.get_driver().on_startup
def setup() -> None:
    for patcher in _PATCHERS:
        patcher.patch()


@nonebot.get_driver().on_shutdown
def dispose() -> None:
    for patcher in _PATCHERS:
        patcher.restore()
