import contextlib
import hashlib

from nonebot import on_startswith, require
from nonebot.adapters import Event
from nonebot.log import logger
from nonebot.permission import SUPERUSER

require("nonebot_plugin_alconna")
require("nonebot_plugin_datastore")
require("nonebot_plugin_orm")
require("nonebot_plugin_apscheduler")
from nonebot_plugin_alconna.uniseg import UniMessage
from nonebot_plugin_alconna.uniseg.utils import fleep
from nonebot_plugin_apscheduler import scheduler

from .cos_ops import delete_file, presign, put_file
from .database import pop_expired, update_key
from .depends import EventImageRaw

upload_cos = on_startswith("cos上传", permission=SUPERUSER)
logger = logger.opt(colors=True)


@upload_cos.handle()
async def _(event: Event, raw: EventImageRaw):
    digest = hashlib.md5(raw).hexdigest()
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
        from ..exe_code.code_context import Context

        Context.get_context(event).set_value("url", url)


@scheduler.scheduled_job("cron", minutes="*/5")
async def _():
    async for key in pop_expired():
        await delete_file(key)
        logger.info(f"删除超时文件: <c>{key}</c>")
