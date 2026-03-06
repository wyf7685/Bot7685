import contextlib
import importlib
from pathlib import Path
from typing import Annotated, Any

from nonebot.adapters import Bot, Event
from nonebot.dependencies import Dependent
from nonebot.matcher import Matcher
from nonebot.params import Depends
from nonebot.typing import T_DependencyCache, T_State
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
            importlib.import_module(f".{name}", __package__)


_load_providers()


async def get_upload_provider(target: Target) -> UploadProvider:
    for provider_cls in sorted(PROVIDERS, key=lambda cls: cls.priority, reverse=True):
        if await provider_cls.verify(target):
            return provider_cls()
    raise ValueError(f"No upload provider found for target {target}")


async def _upload_provider(target: MsgTarget) -> UploadProvider:
    try:
        return await get_upload_provider(target)
    except ValueError:
        Matcher.skip()


Uploader = Annotated[UploadProvider, Depends(_upload_provider)]


async def _extract_provider_extra(
    uploader: Uploader,
    matcher: Matcher,
    bot: Bot,
    event: Event,
    state: T_State,
    stack: contextlib.AsyncExitStack,
    dependency_cache: T_DependencyCache,
) -> dict[str, Any]:
    if uploader.extract_extra is None:
        return {}

    dependent = Dependent[dict[str, Any]].parse(
        call=uploader.extract_extra,
        allow_types=matcher.HANDLER_PARAM_TYPES,
    )
    return await dependent(
        matcher=matcher,
        bot=bot,
        event=event,
        state=state,
        stack=stack,
        dependency_cache=dependency_cache,
    )


UploaderExtra = Annotated[dict[str, Any], Depends(_extract_provider_extra)]
