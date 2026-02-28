import functools
import inspect
from collections.abc import Callable
from typing import Protocol, cast

import nonebot
from nonebot.adapters import Event, Message, MessageSegment

from .config import plugin_config
from .highlight import Highlight

type PatcherCall[T: Event] = Callable[[T], str]


class PatcherHandle[T: Event](Protocol):
    __call__: PatcherCall[T]
    original: PatcherCall[T]

    def patch(self) -> None: ...
    def restore(self) -> None: ...


class Patcher(Protocol):
    def __call__[T: Event](self, call: PatcherCall[T]) -> PatcherHandle[T]: ...
    def bind[TMS: MessageSegment, TM: Message, TE: Event](
        self, highlight_cls: type[Highlight[TMS, TM, TE]], /
    ) -> Patcher: ...


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


def _patcher[TE: Event, TMS: MessageSegment, TM: Message](
    call: PatcherCall[TE],
    highlight_cls: type[Highlight[TMS, TM, TE]],
) -> PatcherHandle[TE]:
    cls: type[TE] = inspect.get_annotations(call)["self"]
    assert issubclass(cls, Event)
    original = cls.get_log_string

    @functools.wraps(call)
    def call_with_event_type(self: TE) -> str:
        return f"[{highlight_cls.event_type(self)}]: {call(self)}"

    wrapper = copy_signature(original, apply_debug_wrapper(call_with_event_type))
    module_name = cls.__module__.replace("nonebot.adapters.", "~")

    def patch() -> None:
        cls.get_log_string = wrapper
        logger.debug(f"Patch <m>{module_name}</m>.<g>{cls.__name__}</g>")

    def restore() -> None:
        cls.get_log_string = original
        logger.debug(f"Restore <m>{module_name}</m>.<g>{cls.__name__}</g>")

    handle = cast("PatcherHandle[TE]", call)
    handle.original = original
    handle.patch = patch
    handle.restore = restore
    _PATCHERS.add(handle)
    return handle


def _make_patcher() -> Patcher:
    def bind[TMS: MessageSegment, TM: Message, TE: Event](
        highlight_cls: type[Highlight[TMS, TM, TE]],
    ) -> Patcher:
        def wrapper(call: PatcherCall[TE]) -> PatcherHandle[TE]:
            return _patcher(call, highlight_cls)

        patcher = cast("Patcher", wrapper)
        patcher.bind = bind
        return patcher

    return bind(Highlight)


patcher = _make_patcher()


@patcher
def patch_base_event(self: Event) -> str:
    return Highlight.apply(self)


@nonebot.get_driver().on_startup
def setup() -> None:
    for patcher in _PATCHERS:
        patcher.patch()


@nonebot.get_driver().on_shutdown
def dispose() -> None:
    for patcher in _PATCHERS:
        patcher.restore()
