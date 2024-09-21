import contextlib

import httpx
from nonebot import get_bots, get_plugin_config, require
from nonebot.adapters.onebot.v11 import Bot, MessageSegment
from nonebot.log import logger
from pydantic import BaseModel, Field

require("nonebot_plugin_apscheduler")
from nonebot_plugin_apscheduler import scheduler


class Config(BaseModel):
    class Time(BaseModel):
        hour: int = Field(default=0, alias="HOUR")
        minute: int = Field(default=0, alias="MINUTE")

    read_qq_friends: list[int] = Field(default_factory=list)
    read_qq_groups: list[int] = Field(default_factory=list)
    read_inform_time: list[Time] = Field(default_factory=list)


config = get_plugin_config(Config)
api_url = ["https://api.2xb.cn/zaob", "https://api.iyk0.com/60s"]


async def get_url(api: str) -> str:
    async with httpx.AsyncClient() as client:
        resp = await client.get(api)
        resp.raise_for_status()
    return resp.json()["imageUrl"]


async def read60s() -> None:
    for api in api_url:
        with contextlib.suppress(Exception):
            url = await get_url(api)
            msg = "今日60S读世界已送达\n" + MessageSegment.image(url)
            break
    else:
        msg = "今日60S读世界获取失败!"

    bot = next((b for b in get_bots().values() if isinstance(b, Bot)), None)

    if bot is None:
        logger.opt(colors=True).warning("未找到 <m>OneBot V11</m> Bot")
        return

    for qq in config.read_qq_friends:
        await bot.send_private_msg(user_id=qq, message=msg)

    for qq_group in config.read_qq_groups:
        await bot.send_group_msg(group_id=qq_group, message=msg)


for time in config.read_inform_time:
    scheduler.add_job(
        read60s,
        "cron",
        hour=time.hour,
        minute=time.minute,
    )
