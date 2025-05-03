import abc
from typing import override

from nonebot.internal.adapter import Bot
from nonebot.typing import T_CalledAPIHook, T_CallingAPIHook

from .plugin import get_current_plugin, internal_dispose


class DisposableBot(Bot, abc.ABC):
    @classmethod
    @override
    def on_calling_api(cls, func: T_CallingAPIHook) -> T_CallingAPIHook:
        if plugin := get_current_plugin():
            internal_dispose(plugin.id_, lambda: cls._calling_api_hook.discard(func))
        return super().on_calling_api(func)

    @classmethod
    @override
    def on_called_api(cls, func: T_CalledAPIHook) -> T_CalledAPIHook:
        if plugin := get_current_plugin():
            internal_dispose(plugin.id_, lambda: cls._called_api_hook.discard(func))
        return super().on_called_api(func)


def setup_disposable() -> None:
    import nonebot.adapters
    import nonebot.internal.adapter

    nonebot.adapters.Bot = nonebot.internal.adapter.Bot = DisposableBot
