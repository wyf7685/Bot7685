import functools
import inspect
from collections.abc import Callable
from typing import Literal, Protocol, cast

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
    __patcher__: Literal[True]

    def __call__[T: Event](self, call: PatcherCall[T]) -> PatcherHandle[T]: ...
    def bind[
        TMS: MessageSegment,
        TM: Message,
        TE: Event,
        TH = type[Highlight[TMS, TM, TE]],
    ](self, highlight_cls: TH, /) -> TH: ...


logger = nonebot.logger.opt(colors=True)
_PATCHER_HANDLES: set[PatcherHandle] = set()


def copy_signature[F: Callable](source: F, target: Callable[..., object], /) -> F:
    return cast("F", functools.update_wrapper(target, source))


def apply_debug_wrapper[T: Event](call: PatcherCall[T]) -> PatcherCall[T]:
    if not plugin_config.patch_event_debug:
        return call

    @functools.wraps(call)
    def wrapper(self: T) -> str:
        logger.debug(Highlight.apply(self))
        return call(self)

    return wrapper


def _patcher_impl[TE: Event, TMS: MessageSegment, TM: Message](
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
    _PATCHER_HANDLES.add(handle)
    return handle


def _make_patcher() -> Patcher:
    def make_wrapper[TMS: MessageSegment, TM: Message, TE: Event](
        highlight_cls: type[Highlight[TMS, TM, TE]],
    ) -> Patcher:
        def patcher_wrapper(call: PatcherCall[TE]) -> PatcherHandle[TE]:
            return _patcher_impl(call, highlight_cls)

        patcher = cast("Patcher", patcher_wrapper)
        patcher.__patcher__ = True
        patcher.bind = bind
        return patcher

    def bind[TH: type[Highlight]](highlight_cls: TH, /) -> TH:
        if (current_frame := inspect.currentframe()) is None:
            raise RuntimeError("Failed to get current frame")
        if (caller_frame := current_frame.f_back) is None:
            raise RuntimeError("Failed to get caller frame")
        gen = (
            name
            for name, value in caller_frame.f_globals.items()
            if getattr(value, "__patcher__", False)
        )
        if (patcher_name := next(gen, None)) is None:
            raise RuntimeError("Failed to find patcher in caller frame")

        caller_frame.f_globals[patcher_name] = make_wrapper(highlight_cls)
        return highlight_cls

    return make_wrapper(Highlight)


patcher = _make_patcher()


@patcher
def patch_base_event(self: Event) -> str:
    return Highlight.apply(self)


@nonebot.get_driver().on_startup
def setup() -> None:
    for patcher in _PATCHER_HANDLES:
        patcher.patch()


@nonebot.get_driver().on_shutdown
def dispose() -> None:
    for patcher in _PATCHER_HANDLES:
        patcher.restore()
