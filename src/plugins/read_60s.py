import contextlib
from collections.abc import Iterable
from typing import Any

import httpx
from msgspec import json as msgjson
from nonebot import require
from nonebot.compat import type_validate_python
from nonebot.log import logger
from nonebot.plugin import PluginMetadata, inherit_supported_adapters
from pydantic import BaseModel, Field

require("nonebot_plugin_alconna")
require("nonebot_plugin_apscheduler")
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

__plugin_meta__ = PluginMetadata(
    name="read_60s",
    description="每日60S读世界",
    usage="每日60S读世界",
    type="application",
    supported_adapters=inherit_supported_adapters("nonebot_plugin_alconna"),
)

config_file = get_plugin_data_file("read_60s.json")


class Read60sConfig(BaseModel):
    class Time(BaseModel):
        hour: int = Field(default=0)
        minute: int = Field(default=0)

    time: Time
    target_data: dict[str, Any]

    @property
    def target(self) -> Target:
        return Target.load(self.target_data)


def read_config() -> list[Read60sConfig]:
    if not config_file.exists():
        return []

    try:
        return type_validate_python(
            list[Read60sConfig],
            msgjson.decode(config_file.read_bytes()),
        )
    except Exception as e:
        logger.opt(colors=True).warning(f"读取配置失败: {e}")
        return []


def save_config(configs: Iterable[Read60sConfig]) -> None:
    encoded = msgjson.encode([config.model_dump(mode="json") for config in configs])
    config_file.write_bytes(encoded)


def add_config(target: Target, hour: int, minute: int) -> Read60sConfig:
    config = Read60sConfig(
        time=Read60sConfig.Time(hour=hour, minute=minute),
        target_data=target.dump(),
    )
    save_config([*read_config(), config])
    return config


def clear_config_for(target: Target) -> None:
    save_config(config for config in read_config() if not target.verify(config.target))


async def get_url(api: str) -> str:
    async with httpx.AsyncClient() as client:
        resp: dict[str, str] = (await client.get(api)).raise_for_status().json()
    return resp["imageUrl"]


async def get_read60s_msg() -> UniMessage:
    async with httpx.AsyncClient() as client:
        for api in "https://api.2xb.cn/zaob", "https://api.iyk0.com/60s":
            with contextlib.suppress(Exception):
                resp: dict[str, str] = (await client.get(api)).raise_for_status().json()
                url = resp["imageUrl"]
                return UniMessage.text("今日60S读世界已送达\n").image(url=url)
    return UniMessage.text("今日60S读世界获取失败!")


def add_job(config: Read60sConfig) -> None:
    @scheduler.scheduled_job(
        CronTrigger(hour=config.time.hour, minute=config.time.minute),
        args=(config.target,),
        id=f"read_60s_{config.time.hour}_{config.time.minute}_{hash(config.target)}",
        misfire_grace_time=60,
    )
    async def _(target: Target) -> None:
        message = await get_read60s_msg()
        await target.send(message)


for config in read_config():
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

    add_job(add_config(target, hour, minute))
    await UniMessage.text(
        f"已添加定时任务，每日{hour}点{minute}分发送60S读世界"
    ).finish()


@matcher.assign("~clear")
async def assign_clear(target: MsgTarget) -> None:
    clear_config_for(target)
    await UniMessage.text("已清空当前会话的定时任务").finish()


@matcher.assign("~list")
async def assign_list(target: MsgTarget) -> None:
    configs = [config for config in read_config() if target.verify(config.target)]
    if not configs:
        await UniMessage.text("当前会话没有定时任务").finish()

    msg = "当前会话的定时任务:\n\n"
    for idx, config in enumerate(configs, 1):
        msg += f"{idx}. {config.time.hour}:{config.time.minute}\n"
    await UniMessage.text(msg).finish()


@matcher.assign("~get")
async def assign_get() -> None:
    await (await get_read60s_msg()).finish()
