import contextlib

import httpx
from nonebot import get_bots, get_plugin_config, require
from nonebot.adapters.onebot.v11 import Bot, Message, MessageSegment
from nonebot.log import logger
from nonebot.plugin import PluginMetadata
from pydantic import BaseModel, Field

require("nonebot_plugin_apscheduler")
from apscheduler.triggers.cron import CronTrigger
from nonebot_plugin_apscheduler import scheduler

__plugin_meta__ = PluginMetadata(
    name="read_60s",
    description="每日60S读世界",
    usage="每日60S读世界",
    type="application",
    supported_adapters={"~onebot.v11"},
)


class Read60sConfig(BaseModel):
    class Time(BaseModel):
        hour: int = Field(default=0)
        minute: int = Field(default=0)

    time: Time
    user_id: list[int] = []
    group_id: list[int] = []


class Config(BaseModel):
    read_60s: list[Read60sConfig] = []


async def get_url(api: str) -> str:
    async with httpx.AsyncClient() as client:
        resp: dict[str, str] = (await client.get(api)).raise_for_status().json()
    return resp["imageUrl"]


async def read60s(config: Read60sConfig) -> None:
    for api in "https://api.2xb.cn/zaob", "https://api.iyk0.com/60s":
        with contextlib.suppress(Exception):
            url = await get_url(api)
            msg = "今日60S读世界已送达\n" + MessageSegment.image(url)
            break
    else:
        msg = Message("今日60S读世界获取失败!")

    bot = next((b for b in get_bots().values() if isinstance(b, Bot)), None)

    if bot is None:
        logger.opt(colors=True).warning("未找到 <m>OneBot V11</m> Bot")
        return

    for user_id in config.user_id:
        await bot.send_private_msg(user_id=user_id, message=msg)

    for group_id in config.group_id:
        await bot.send_group_msg(group_id=group_id, message=msg)


for config in get_plugin_config(Config).read_60s:
    scheduler.add_job(
        read60s,
        CronTrigger(hour=config.time.hour, minute=config.time.minute),
        args=(config,),
    )
