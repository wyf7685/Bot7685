from hashlib import sha256

from nonebot import on_startswith, require
from nonebot.adapters import Bot, Event
from nonebot.permission import SUPERUSER
from nonebot.typing import T_State

require("nonebot_plugin_alconna")
require("nonebot_plugin_datastore")
from nonebot_plugin_alconna.uniseg import Image, UniMessage, image_fetch
from nonebot_plugin_alconna.uniseg.utils import fleep

from .cos_ops import presign, put_file

upload_cos = on_startswith("cos上传", permission=SUPERUSER)
KEY = "upload_cos_image"


@upload_cos.got(KEY, "请发送图片")
async def _(bot: Bot, event: Event, state: T_State):
    msg = await UniMessage.generate(message=state[KEY])
    if not msg.has(Image):
        await upload_cos.finish("图片获取失败")

    raw = await image_fetch(event, bot, state, msg[Image, 0])
    if not isinstance(raw, bytes):
        await upload_cos.finish("图片获取失败")

    key = f"{sha256(raw).hexdigest()}.{fleep.get(raw).extensions[0]}"
    await put_file(raw, key)
    url = await presign(key)
    await UniMessage(url).send(reply_to=True)
