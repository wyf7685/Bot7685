import hashlib

from nonebot import logger
from nonebot_plugin_alconna import UniMessage
from nonebot_plugin_alconna.uniseg.utils import fleep

from src.service.s3 import get_s3_service

from .depends import EventImageRaw
from .matcher import s3_upload

_UPLOAD_TTL_SECONDS = 3600


@s3_upload.handle()
async def handle_upload(raw: EventImageRaw) -> None:
    digest = hashlib.md5(raw).hexdigest()  # noqa: S324
    extensions = fleep.get(raw).extensions
    extension = extensions[0] if extensions else "bin"
    key = f"manual/{digest[:2]}/{digest}.{extension}"
    try:
        url = await get_s3_service().upload_temporary(
            raw,
            key=key,
            expires_in=_UPLOAD_TTL_SECONDS,
        )
    except Exception:
        logger.exception("S3 image upload failed")
        await UniMessage.text("上传图片失败，请稍后重试。").finish(reply_to=True)
    await UniMessage.text(url).finish(reply_to=True)


__all__ = []
