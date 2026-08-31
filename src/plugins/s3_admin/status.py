from nonebot_plugin_alconna import UniMessage

from src.service.s3 import get_s3_service

from .formatting import format_status
from .matcher import s3_admin


@s3_admin.assign("status")
async def handle_status() -> None:
    service = get_s3_service()
    snapshot = await service.configuration_snapshot()
    connected = await service.ping() if snapshot.config is not None else None
    await UniMessage.text(format_status(snapshot, connected=connected)).finish()


__all__ = []
