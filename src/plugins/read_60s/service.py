import contextlib
from datetime import datetime

import httpx2
from nonebot_plugin_alconna import UniMessage


async def get_read60s_msg() -> UniMessage:
    with contextlib.suppress(Exception):
        async with httpx2.AsyncClient() as client:
            url = f"https://60s-static.viki.moe/images/{datetime.now():%Y-%m-%d}.png"
            response = (await client.get(url)).raise_for_status()
        return UniMessage.text("今日60S读世界已送达\n").image(raw=response.content)
    return UniMessage.text("今日60S读世界获取失败!")


__all__ = ["get_read60s_msg"]
