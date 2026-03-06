from typing import Any, final, override

import anyio
from nonebot_plugin_alconna import Target, UniMessage

from ..base import UploadProvider


@final
class DefaultUploadProvider(UploadProvider):
    priority = -1

    @override
    @classmethod
    async def verify(cls, target: Target) -> bool:
        return True

    @override
    async def do_upload(
        self,
        file: anyio.Path,
        name: str,
        target: Target,
        extra: dict[str, Any],
    ) -> None:
        await UniMessage.file(raw=await file.read_bytes(), name=name).send(target)
