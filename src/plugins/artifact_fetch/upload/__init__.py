import contextlib
import importlib
from pathlib import Path
from typing import Annotated, Any

from nonebot import logger
from nonebot.adapters import Bot, Event
from nonebot.dependencies import Dependent
from nonebot.internal.params import DependencyCache
from nonebot.matcher import Matcher
from nonebot.params import Depends
from nonebot.typing import T_State, _DependentCallable
from nonebot_plugin_alconna import MsgTarget, Target

from .base import PROVIDERS, UploadProvider


def _load_providers() -> None:
    module_names = [
        path.stem
        for path in Path(__file__).parent.joinpath("providers").iterdir()
        if path.is_file() and path.suffix == ".py" and not path.stem.startswith("_")
    ]

    for name in module_names:
        with contextlib.suppress(ImportError):
            importlib.import_module(f".providers.{name}", __package__)
            logger.debug(f"Upload provider module '{name}' loaded.")


_load_providers()


async def get_upload_provider(target: Target) -> UploadProvider:
    for provider_cls in sorted(PROVIDERS, key=lambda cls: cls.priority, reverse=True):
        if await provider_cls.verify(target):
            return provider_cls()
    raise ValueError(f"No upload provider found for target {target}")


async def _upload_provider(target: MsgTarget) -> UploadProvider:
    try:
        return await get_upload_provider(target)
    except ValueError as e:
        logger.warning(e)
        Matcher.skip()


Uploader = Annotated[UploadProvider, Depends(_upload_provider)]


_extractor_dependent_cache: dict[int, Dependent[dict[str, Any]]] = {}
T_DependencyCache = dict[_DependentCallable[Any], DependencyCache]


async def _extract_provider_extra(
    uploader: Uploader,
    matcher: Matcher,
    bot: Bot,
    event: Event,
    state: T_State,
    stack: contextlib.AsyncExitStack,
    dependency_cache: T_DependencyCache | None = None,
) -> dict[str, Any]:
    if (call := type(uploader).extract_extra) is None:
        return {}

    cache_key = hash((id(call), *(id(param) for param in matcher.HANDLER_PARAM_TYPES)))
    if cache_key not in _extractor_dependent_cache:
        _extractor_dependent_cache[cache_key] = Dependent[dict[str, Any]].parse(
            call=call,
            allow_types=matcher.HANDLER_PARAM_TYPES,
        )
    dependent = _extractor_dependent_cache[cache_key]

    return await dependent(
        matcher=matcher,
        bot=bot,
        event=event,
        state=state,
        stack=stack,
        dependency_cache=dependency_cache,
    )


UploaderExtra = Annotated[dict[str, Any], Depends(_extract_provider_extra)]
