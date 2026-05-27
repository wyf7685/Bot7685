import contextlib
from copy import deepcopy
from typing import Annotated, Any

from nonebot import logger, on_message, require
from nonebot.adapters import Bot, discord
from nonebot.params import Depends
from nonebot.permission import SuperUser
from nonebot.typing import T_State
from pydantic import BaseModel

from src.plugins.neuro_schedule.models import ScheduleData
from src.utils import ConfigModelFile

require("nonebot_plugin_alconna")
require("nonebot_plugin_htmlrender")
require("nonebot_plugin_localstore")
from nonebot_plugin_alconna import (
    Alconna,
    MsgTarget,
    Subcommand,
    SupportScope,
    Target,
    UniMessage,
    on_alconna,
)
from nonebot_plugin_localstore import get_plugin_config_file, get_plugin_data_file

from .parser import parse_schedule
from .render import render_schedule


class Config(BaseModel):
    recv_target: dict[str, Any] | None = None
    send_target: dict[str, Any] | None = None

    @property
    def recv(self) -> Target | None:
        return Target.load(deepcopy(self.recv_target)) if self.recv_target else None

    @property
    def send(self) -> Target | None:
        return Target.load(deepcopy(self.send_target)) if self.send_target else None


config_file = ConfigModelFile(get_plugin_config_file("config.json"), Config)
schedule_data_file = get_plugin_data_file("schedule.json")

cmd = on_alconna(
    Alconna(
        "neuro_schedule",
        Subcommand("recv", help_text="设置当前会话为接收端"),
        Subcommand("send", help_text="设置当前会话为发送端"),
    ),
    aliases={"neuro-schedule"},
)
IsSuperUser = Annotated[bool, Depends(SuperUser())]


@cmd.assign("~recv")
async def assign_recv(bot: Bot, target: MsgTarget, is_superuser: IsSuperUser) -> None:
    if not is_superuser:
        await UniMessage.text("只有管理员可以设置接收端").finish()
    if not isinstance(bot, discord.Bot):
        await UniMessage.text("当前会话不支持设置为接收端").finish()

    config = config_file.load()
    config.recv_target = target.dump()
    config_file.save(config)
    await UniMessage.text("设置当前会话为接收端").finish()


@cmd.assign("~send")
async def assign_send(target: MsgTarget, is_superuser: IsSuperUser) -> None:
    if not is_superuser:
        await UniMessage.text("只有管理员可以设置发送端").finish()
    if target.scope != SupportScope.qq_client:
        await UniMessage.text("当前会话不支持设置为发送端").finish()

    config = config_file.load()
    config.send_target = target.dump()
    config_file.save(config)
    await UniMessage.text("设置当前会话为发送端").finish()


@cmd.handle()
async def handle_cmd() -> None:
    if not schedule_data_file.exists():
        await UniMessage.text("当前没有存档的日程数据").finish()
    try:
        data = ScheduleData.model_validate_json(schedule_data_file.read_bytes())
    except Exception:
        logger.exception("读取日程数据失败")
        await UniMessage.text("读取日程数据失败").finish()

    rendered = await render_schedule(data)
    unimsg = UniMessage.image(raw=rendered)
    if data.schedule_image and data.schedule_image.exists():
        unimsg.image(raw=data.schedule_image.read_bytes())
    await unimsg.finish()


@on_message
async def forward(
    _: discord.MessageCreateEvent,
    target: MsgTarget,
    state: T_State,
) -> bool:
    if (
        (send := (config := config_file.load()).send) is None
        or (recv := config.recv) is None
        or not recv.verify(target)
    ):
        return False

    try:
        bot = await send.select()
    except Exception:
        logger.opt(exception=True).warning("无法获取目标 Bot，跳过转发")
        return False

    state["dst"] = (send, bot)
    return True


@forward.handle()
async def handle_forward(event: discord.MessageCreateEvent, state: T_State) -> None:
    data = await parse_schedule(event.get_message())

    if schedule_data_file.exists():  # TODO: merge?
        with contextlib.suppress(Exception):
            existing = ScheduleData.model_validate_json(schedule_data_file.read_bytes())
            if existing.schedule_image:
                existing.schedule_image.unlink(missing_ok=True)
    schedule_data_file.write_text(data.model_dump_json(), encoding="utf-8")
    rendered = await render_schedule(data)

    unimsg = UniMessage.image(raw=rendered)
    if data.schedule_image and data.schedule_image.exists():
        unimsg.image(raw=data.schedule_image.read_bytes())
    await unimsg.send(*state["dst"])
