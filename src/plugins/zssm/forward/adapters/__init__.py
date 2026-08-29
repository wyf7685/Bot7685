import asyncio
import importlib
from collections.abc import Sequence
from typing import cast

from nonebot.adapters import Bot, Event
from nonebot_plugin_alconna import Reference, UniMessage

from ..contracts import (
    AdapterReferenceResolver,
    ForwardFetchError,
    ForwardInputError,
    ForwardReferenceResolver,
    ForwardUnsupportedError,
)

_ADAPTER_MODULES = {
    "Milky": "milky",
    "OneBot V11": "onebot11",
    "Satori": "satori",
}


def _load_resolver(adapter_name: str) -> AdapterReferenceResolver:
    module_name = _ADAPTER_MODULES.get(adapter_name)
    if module_name is None:
        raise ForwardUnsupportedError(
            "adapter does not expose forwarded-message retrieval"
        )
    try:
        module = importlib.import_module(f"{__package__}.{module_name}")
        resolver = module.resolve
    except (AttributeError, ImportError) as error:
        raise ForwardUnsupportedError(
            f"{adapter_name} forwarded-message resolver is unavailable"
        ) from error
    if not callable(resolver):
        raise ForwardUnsupportedError(
            f"{adapter_name} forwarded-message resolver is unavailable"
        )
    return cast("AdapterReferenceResolver", resolver)


def create_adapter_reference_resolver(
    bot: Bot,
    event: Event,
    *,
    timeout_seconds: float,
) -> ForwardReferenceResolver:
    adapter_name = bot.adapter.get_name()
    resolver = _load_resolver(adapter_name)

    async def resolve(reference: Reference) -> Sequence[UniMessage]:
        try:
            async with asyncio.timeout(timeout_seconds):
                return await resolver(bot, event, reference)
        except asyncio.CancelledError:
            raise
        except ForwardInputError:
            raise
        except Exception as error:
            raise ForwardFetchError(
                f"{adapter_name} forwarded-message retrieval failed"
            ) from error

    return resolve


__all__ = ["create_adapter_reference_resolver"]
