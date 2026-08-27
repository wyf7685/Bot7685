import asyncio
from collections.abc import Mapping, Sequence

from ....http_transport import ValidatedHttpTarget
from .bilibili import BilibiliAdapter
from .contracts import SourceAdapter, SourceIO, SourceTarget
from .pixiv import PixivAdapter
from .twitter import TwitterAdapter


class SourceRegistry:
    def __init__(self, adapters: Sequence[SourceAdapter]) -> None:
        self._adapters = tuple(adapters)

    def match(
        self,
        target: ValidatedHttpTarget,
    ) -> tuple[SourceAdapter, SourceTarget] | None:
        for adapter in self._adapters:
            source_target = adapter.recognize(target)
            if source_target is not None:
                return adapter, source_target
        return None

    async def resolve_card_urls(
        self,
        urls: Sequence[str],
        io: SourceIO,
    ) -> Mapping[str, str]:
        unique_urls = tuple(dict.fromkeys(urls))
        if not unique_urls:
            return {}
        resolved: dict[str, str] = {}

        async def resolve_one(url: str) -> None:
            for adapter in self._adapters:
                try:
                    canonical = await adapter.resolve_card_url(url, io)
                except asyncio.CancelledError:
                    raise
                except Exception:  # noqa: S112 - unsupported adapters are skipped
                    continue
                if canonical is not None:
                    resolved[url] = canonical
                    return

        async with asyncio.TaskGroup() as tasks:
            for url in unique_urls:
                tasks.create_task(resolve_one(url))
        return resolved


DEFAULT_SOURCE_REGISTRY = SourceRegistry(
    (TwitterAdapter(), BilibiliAdapter(), PixivAdapter())
)


__all__ = ["DEFAULT_SOURCE_REGISTRY", "SourceRegistry"]
