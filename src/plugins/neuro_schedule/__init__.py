from typing import Annotated, Any

from nonebot import logger, on_message, require
from nonebot.adapters import Bot, discord
from nonebot.adapters.onebot import v11
from nonebot.params import Depends
from nonebot.permission import SUPERUSER
from pydantic import BaseModel

require("nonebot_plugin_alconna")
require("nonebot_plugin_htmlrender")
require("nonebot_plugin_localstore")
from nonebot_plugin_alconna import (
    Alconna,
    Image,
    MsgTarget,
    Subcommand,
    Target,
    UniMessage,
    on_alconna,
)
from nonebot_plugin_localstore import get_plugin_config_file

require("src.plugins.group_pipe")
from src.plugins.group_pipe import get_sender
from src.plugins.group_pipe.adapters.discord import MessageConverter
from src.utils import ConfigModelFile

from .render import render_schedule


class Config(BaseModel):
    recv_target: dict[str, Any] | None = None
    send_target: dict[str, Any] | None = None

    @property
    def recv(self) -> Target | None:
        return Target.load(self.recv_target) if self.recv_target else None

    @property
    def send(self) -> Target | None:
        return Target.load(self.send_target) if self.send_target else None


config_file = ConfigModelFile(get_plugin_config_file("config.json"), Config)

setup_cmd = on_alconna(
    Alconna(
        "neuro_schedule",
        Subcommand("recv", help_text="设置当前会话为接收端"),
        Subcommand("send", help_text="设置当前会话为发送端"),
    ),
    permission=SUPERUSER,
)


@setup_cmd.assign("~recv")
async def assign_recv(target: MsgTarget, _: discord.Bot) -> None:
    config = config_file.load()
    config.recv_target = target.dump()
    config_file.save(config)
    await setup_cmd.send("设置当前会话为接收端")


@setup_cmd.assign("~send")
async def assign_send(target: MsgTarget, _: v11.Bot) -> None:
    config = config_file.load()
    config.send_target = target.dump()
    config_file.save(config)
    await setup_cmd.send("设置当前会话为发送端")


@on_message
def forward(target: MsgTarget) -> bool:
    return (
        (config := config_file.load()).send is not None
        and (recv := config.recv) is not None
        and recv.verify(target)
    )


async def _dst() -> tuple[Target, Bot]:
    if (target := config_file.load().send) is None:
        forward.skip()

    try:
        bot = await target.select()
    except Exception:
        logger.opt(exception=True).warning("无法获取目标 Bot，跳过转发")
        forward.skip()

    return target, bot


@forward.handle()
async def handle_forward(
    src_bot: discord.Bot,
    event: discord.MessageCreateEvent,
    dst: Annotated[tuple[Target, Bot], Depends(_dst)],
) -> None:
    msg = await MessageConverter.get_message(event)
    if not msg:
        logger.warning("消息提取结果为空，跳过转发")
        return

    unimsg = await MessageConverter(src_bot).convert(msg)
    if not unimsg:
        logger.warning("消息转换结果为空，跳过转发")
        return

    schedule_img = unimsg[Image, -1]
    unimsg.remove(schedule_img)
    rendered = await render_schedule(unimsg.split("\n"))
    unimsg = UniMessage.image(raw=rendered) + schedule_img

    target, dst_bot = dst
    await get_sender(dst_bot).send(dst_bot, target, unimsg)
