from hashlib import sha256

from nonebot import on_startswith, require
from nonebot.adapters import Bot, Event
from nonebot.permission import SUPERUSER
from nonebot.typing import T_State

require("nonebot_plugin_alconna")
require("nonebot_plugin_datastore")
from nonebot_plugin_alconna.uniseg import UniMessage, image_fetch
from nonebot_plugin_alconna.uniseg.utils import fleep

from .cos_ops import presign, put_file
from .depends import EventImage

upload_cos = on_startswith("cos上传", permission=SUPERUSER)


@upload_cos.handle()
async def _(bot: Bot, event: Event, state: T_State, image: EventImage):
    raw = await image_fetch(event, bot, state, image)
    if not isinstance(raw, bytes):
        await upload_cos.finish("图片获取失败")

    digest = sha256(raw).hexdigest()
    key = f"{digest[:2]}/{digest}.{fleep.get(raw).extensions[0]}"
    try:
        await put_file(raw, key)
    except Exception as err:
        await UniMessage(f"上传图片失败: {err!r}").send(reply_to=True)

    url = await presign(key)
    await UniMessage(url).send(reply_to=True)
