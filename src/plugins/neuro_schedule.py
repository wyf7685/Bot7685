from typing import TYPE_CHECKING, Any

from nonebot import on_message, require
from nonebot.adapters import discord
from nonebot.adapters.onebot import v11
from nonebot.permission import SUPERUSER
from pydantic import BaseModel

require("nonebot_plugin_alconna")
require("nonebot_plugin_localstore")
from nonebot_plugin_alconna import Alconna, MsgTarget, Subcommand, Target, on_alconna
from nonebot_plugin_localstore import get_plugin_config_file

require("src.plugins.group_pipe")
from src.plugins.group_pipe.adapter import get_sender
from src.plugins.group_pipe.adapters.discord import MessageConverter
from src.utils import ConfigModelFile


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


def check_is_recv(target: MsgTarget) -> bool:
    return (
        (config := config_file.load()).send is not None
        and (recv := config.recv) is not None
        and recv.verify(target)
    )


forward = on_message(check_is_recv)


@forward.handle()
async def handle_forward(
    src_bot: discord.Bot,
    event: discord.MessageCreateEvent,
) -> None:
    msg = await MessageConverter(src_bot).convert(event.get_message())
    if not msg:
        return

    target = config_file.load().send
    if TYPE_CHECKING:
        assert target is not None  # checked in rule

    dst_bot = await target.select()
    await get_sender(dst_bot).send(dst_bot, target, msg)
