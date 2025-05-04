from typing import Any

from nonebot.dependencies import Dependent
from nonebot.message import (
    EVENT_PCS_PARAMS,
    RUN_POSTPCS_PARAMS,
    RUN_PREPCS_PARAMS,
    _event_postprocessors,  # pyright: ignore[reportPrivateUsage]
    _event_preprocessors,  # pyright: ignore[reportPrivateUsage]
    _run_postprocessors,  # pyright: ignore[reportPrivateUsage]
    _run_preprocessors,  # pyright: ignore[reportPrivateUsage]
)
from nonebot.typing import (
    T_EventPostProcessor,
    T_EventPreProcessor,
    T_RunPostProcessor,
    T_RunPreProcessor,
)

from .common import get_current_plugin, internal_dispose


def event_preprocessor(func: T_EventPreProcessor) -> T_EventPreProcessor:
    """事件预处理。

    装饰一个函数，使它在每次接收到事件并分发给各响应器之前执行。
    """
    dependent = Dependent[Any].parse(call=func, allow_types=EVENT_PCS_PARAMS)
    _event_preprocessors.add(dependent)
    if plugin := get_current_plugin():
        internal_dispose(plugin.id_, lambda: _event_preprocessors.discard(dependent))
    return func


def event_postprocessor(func: T_EventPostProcessor) -> T_EventPostProcessor:
    """事件后处理。

    装饰一个函数，使它在每次接收到事件并分发给各响应器之后执行。
    """
    dependent = Dependent[Any].parse(call=func, allow_types=EVENT_PCS_PARAMS)
    _event_postprocessors.add(dependent)
    if plugin := get_current_plugin():
        internal_dispose(plugin.id_, lambda: _event_postprocessors.discard(dependent))
    return func


def run_preprocessor(func: T_RunPreProcessor) -> T_RunPreProcessor:
    """运行预处理。

    装饰一个函数，使它在每次事件响应器运行前执行。
    """
    dependent = Dependent[Any].parse(call=func, allow_types=RUN_PREPCS_PARAMS)
    _run_preprocessors.add(dependent)
    if plugin := get_current_plugin():
        internal_dispose(plugin.id_, lambda: _run_preprocessors.discard(dependent))
    return func


def run_postprocessor(func: T_RunPostProcessor) -> T_RunPostProcessor:
    """运行后处理。

    装饰一个函数，使它在每次事件响应器运行后执行。
    """
    dependent = Dependent[Any].parse(call=func, allow_types=RUN_POSTPCS_PARAMS)
    _run_postprocessors.add(dependent)
    if plugin := get_current_plugin():
        internal_dispose(plugin.id_, lambda: _run_postprocessors.discard(dependent))
    return func


def setup_disposable() -> None:
    import nonebot.message

    nonebot.message.event_preprocessor = event_preprocessor
    nonebot.message.event_postprocessor = event_postprocessor
    nonebot.message.run_preprocessor = run_preprocessor
    nonebot.message.run_postprocessor = run_postprocessor
