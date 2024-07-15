import contextlib
from hashlib import sha256

from nonebot import on_startswith, require
from nonebot.adapters import Event
from nonebot.permission import SUPERUSER

require("nonebot_plugin_alconna")
require("nonebot_plugin_datastore")
from nonebot_plugin_alconna.uniseg import UniMessage
from nonebot_plugin_alconna.uniseg.utils import fleep

from .cos_ops import presign, put_file
from .depends import EventImageRaw

upload_cos = on_startswith("cos上传", permission=SUPERUSER)


@upload_cos.handle()
async def _(event:Event, raw: EventImageRaw):
    digest = sha256(raw).hexdigest()
    key = f"{digest[:2]}/{digest}.{fleep.get(raw).extensions[0]}"
    try:
        await put_file(raw, key)
    except Exception as err:
        await UniMessage(f"上传图片失败: {err!r}").send(reply_to=True)

    url = await presign(key)
    await UniMessage(url).send(reply_to=True)

    with contextlib.suppress(ImportError):
        from src.plugins.exe_code.code_context import Context

        Context.get_context(event).set_value("url", url)
