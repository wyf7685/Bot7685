import abc
from collections.abc import Awaitable, Callable
from typing import Any, ClassVar

import anyio
from nonebot import logger
from nonebot.adapters import Bot, Event
from nonebot_plugin_alconna import Target, UniMessage

PROVIDERS: set[type[UploadProvider]] = set()


class UploadProvider[TB: Bot, TE: Event](abc.ABC):
    priority: ClassVar[int] = 0
    extract_extra: ClassVar[Callable[..., Awaitable[dict[str, Any]]] | None] = None

    def __init_subclass__(cls, **kwargs: object) -> None:
        super().__init_subclass__(**kwargs)
        PROVIDERS.add(cls)

    @classmethod
    @abc.abstractmethod
    async def verify(cls, target: Target) -> bool:
        raise NotImplementedError

    @abc.abstractmethod
    async def do_upload(
        self,
        file: anyio.Path,
        name: str,
        target: Target,
        extra: dict[str, Any],
    ) -> None:
        raise NotImplementedError

    async def upload(
        self,
        file: anyio.Path,
        name: str,
        target: Target,
        extra: dict[str, Any],
    ) -> None:
        if not await file.exists():
            logger.warning(
                f"Artifact {name} was not downloaded successfully, skipping upload"
            )
            return

        try:
            await self.do_upload(file, name, target, extra)
        except Exception as exc:
            logger.exception(f"Failed to upload artifact {name}")
            await UniMessage.text(f"上传 artifact {name} 失败\n{exc!r}").send(target)
