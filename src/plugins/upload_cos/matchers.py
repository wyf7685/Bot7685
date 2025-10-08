import contextlib
import hashlib
from typing import TYPE_CHECKING

from nonebot import on_startswith
from nonebot.log import logger
from nonebot.permission import SUPERUSER
from nonebot_plugin_alconna import Alconna, Args, Match, on_alconna
from nonebot_plugin_alconna.uniseg import At, UniMessage
from nonebot_plugin_alconna.uniseg.utils import fleep

from .cos_ops import presign, put_file
from .database import update_key, update_permission
from .depends import ALLOW_UPLOAD, EventImageRaw

if TYPE_CHECKING:
    from nonebot.adapters import Event

upload_cos = on_startswith("cos上传", permission=ALLOW_UPLOAD)
update_perm = on_alconna(
    Alconna("cos加权", Args["target", At], Args["expired?", int]),
    permission=SUPERUSER,
)
logger = logger.opt(colors=True)


@upload_cos.handle()
async def _(event: Event, raw: EventImageRaw) -> None:
    digest = hashlib.md5(raw).hexdigest()  # noqa: S324
    key = f"{digest[:2]}/{digest}.{fleep.get(raw).extensions[0]}"
    try:
        await put_file(raw, key)
    except Exception as err:
        await UniMessage(f"上传图片失败: {err!r}").send(reply_to=True)

    expired = 3600
    await update_key(key, expired)
    url = await presign(key, expired)
    logger.success(f"预签名URL: <y>{url}</y>")
    await UniMessage(url).send(reply_to=True)

    with contextlib.suppress(ImportError):
        from nonebot_plugin_exe_code.context import Context

        Context.get_context(event).set_value("url", url)


@update_perm.handle()
async def _(target: Match[At], expired: Match[int]) -> None:
    if not target.available:
        return
    user_id = target.result.target
    expire = expired.result if expired.available else 60
    await update_permission(user_id, expire)
    await UniMessage("临时授权").at(user_id).text(f": {expire}s").send(reply_to=True)
