import contextlib
import functools
from typing import Any

import httpx
from nonebot import require
from nonebot.plugin import PluginMetadata, inherit_supported_adapters
from pydantic import BaseModel, Field

require("nonebot_plugin_alconna")
require("nonebot_plugin_apscheduler")
require("nonebot_plugin_localstore")
from apscheduler.triggers.cron import CronTrigger
from nonebot_plugin_alconna import (
    Alconna,
    Args,
    CommandMeta,
    MsgTarget,
    Subcommand,
    Target,
    UniMessage,
    on_alconna,
)
from nonebot_plugin_apscheduler import scheduler
from nonebot_plugin_localstore import get_plugin_data_file

require("src.plugins.trusted")
from src.plugins.trusted import TrustedUser
from src.utils import ConfigListFile

__plugin_meta__ = PluginMetadata(
    name="read_60s",
    description="每日60S读世界",
    usage="每日60S读世界",
    type="application",
    supported_adapters=inherit_supported_adapters("nonebot_plugin_alconna"),
)


class Read60sConfig(BaseModel):
    hour: int = Field(default=0)
    minute: int = Field(default=0)
    target_data: dict[str, Any]

    @functools.cached_property
    def target(self) -> Target:
        return Target.load(self.target_data)


config_file = ConfigListFile(get_plugin_data_file("read_60s.json"), Read60sConfig)


async def get_read60s_msg() -> UniMessage:
    with contextlib.suppress(Exception):
        async with httpx.AsyncClient() as client:
            resp = (await client.get("https://api.2xb.cn/zaob")).raise_for_status()
            url = resp.json()["imageUrl"]
        return UniMessage.text("今日60S读世界已送达\n").image(url=url)
    return UniMessage.text("今日60S读世界获取失败!")


def add_job(config: Read60sConfig) -> None:
    @scheduler.scheduled_job(
        CronTrigger(hour=config.hour, minute=config.minute),
        args=(config.target,),
        id=f"read_60s_{config.hour}_{config.minute}_{hash(config.target)}",
        misfire_grace_time=60,
    )
    async def _(target: Target) -> None:
        await target.send(await get_read60s_msg())


for config in config_file.load():
    add_job(config)


alc = Alconna(
    "read60s",
    Subcommand(
        "add",
        Args["hour", int]["minute", int],
        help_text="在当前会话添加定时任务",
    ),
    Subcommand("clear", help_text="清空当前会话的定时任务"),
    Subcommand("list", help_text="查看定时任务"),
    Subcommand("get", help_text="获取今日60S读世界"),
    meta=CommandMeta(
        description="每日60S读世界",
        usage="read60s add [hour] [minute]\nread60s <clear|list|get>",
        example="read60s add 8 0\nread60s clear\nread60s list\nread60s get",
        author="wyf7685",
    ),
)
matcher = on_alconna(alc, permission=TrustedUser())


@matcher.assign("~add")
async def assign_add(target: MsgTarget, hour: int, minute: int) -> None:
    if not (0 <= hour < 24 and 0 <= minute < 60):
        await UniMessage.text("时间格式错误，请输入正确的时间").finish()

    config = Read60sConfig(
        hour=hour,
        minute=minute,
        target_data=target.dump(),
    )
    config_file.add(config)
    add_job(config)
    await UniMessage.text(
        f"已添加定时任务，每日{hour}点{minute}分发送60S读世界"
    ).finish()


@matcher.assign("~clear")
async def assign_clear(target: MsgTarget) -> None:
    config_file.save(
        [config for config in config_file.load() if not target.verify(config.target)]
    )
    await UniMessage.text("已清空当前会话的定时任务").finish()


@matcher.assign("~list")
async def assign_list(target: MsgTarget) -> None:
    configs = [c for c in config_file.load() if target.verify(c.target)]
    if not configs:
        await UniMessage.text("当前会话没有定时任务").finish()

    msg = "当前会话的定时任务:\n\n"
    for idx, config in enumerate(configs, 1):
        msg += f"{idx}. {config.hour}:{config.minute}\n"
    await UniMessage.text(msg).finish()


@matcher.assign("~get")
async def assign_get() -> None:
    await (await get_read60s_msg()).finish()
