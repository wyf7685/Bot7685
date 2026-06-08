from typing import Literal

import anyio
from nonebot import logger, require
from nonebot.adapters import Event
from nonebot.exception import ActionFailed, MatcherException, NetworkError
from nonebot.matcher import Matcher
from nonebot.params import Depends
from nonebot.permission import SUPERUSER, User
from nonebot.plugin import PluginMetadata, inherit_supported_adapters

require("nonebot_plugin_alconna")
require("nonebot_plugin_localstore")
require("nonebot_plugin_waiter")
import nonebot_plugin_waiter.unimsg as waiter
from nonebot_plugin_alconna import (
    Alconna,
    Args,
    MsgTarget,
    SupportScope,
    UniMessage,
    on_alconna,
)

require("src.service.cache")
require("src.plugins.trusted")
from src.plugins.trusted import TrustedUser

from .common import Downloader
from .jm import JmDownloader
from .pixiv import PixivDownloader
from .utils import format_exc_msg

__plugin_meta__ = PluginMetadata(
    name="jmcomic",
    description="jmcomic",
    usage="/jm <album_id: int>",
    supported_adapters=inherit_supported_adapters("nonebot_plugin_alconna"),
    type="application",
)


cmd_jm = on_alconna(
    Alconna("jm", Args["album_id", int]),
    permission=TrustedUser(),
)
cmd_pixiv = on_alconna(
    Alconna("getpixiv", Args["illust_id", int]),
    permission=TrustedUser(),
)


async def _check_qq_client(target: MsgTarget) -> None:
    if target.scope != SupportScope.qq_client:
        logger.warning(f"不支持的消息目标: {target.scope}")
        Matcher.skip()


async def wait_for_terminate(event: Event, id: int) -> None:
    words = {"terminate", "stop", "cancel", "中止", "停止", "取消"}

    def waiter_rule(e: Event) -> bool:
        return e.get_message().extract_plain_text().strip() in words

    @waiter.waiter(
        [type(event)],
        keep_session=False,
        rule=waiter_rule,
        permission=SUPERUSER | User.from_event(event, perm=cmd_jm.permission),
        block=True,
    )
    def wait() -> Literal[True]:
        return True

    while True:
        if await wait.wait():
            await UniMessage.text(f"中止 {id} 的下载任务").finish(reply_to=True)


async def send_as_forward(event: Event, id: int, downloader: Downloader) -> None:
    receipt = await UniMessage.text(f"开始 {id} 的下载任务…").send(reply_to=True)

    async def send() -> None:
        try:
            await downloader.send_forward(id, event.get_user_id(), receipt)
        finally:
            tg.cancel_scope.cancel()

    async def handle_exc(exc_group: ExceptionGroup, msg: str) -> None:
        logger.opt(exception=exc_group).warning(msg)
        await UniMessage.text(format_exc_msg(msg, exc_group)).finish(reply_to=True)

    try:
        async with anyio.create_task_group() as tg:
            tg.start_soon(wait_for_terminate, event, id)
            await send()
    except* MatcherException:
        raise
    except* (ActionFailed, NetworkError) as exc_group:
        await handle_exc(exc_group, "发送失败")
    except* Exception as exc_group:
        await handle_exc(exc_group, "下载失败")
    else:
        await UniMessage.text(f"完成 {id} 的下载任务").finish(reply_to=True)


@cmd_jm.assign("album_id", parameterless=[Depends(_check_qq_client)])
async def handle_jm(event: Event, album_id: int) -> None:
    await send_as_forward(event, album_id, JmDownloader())


@cmd_pixiv.assign("illust_id", parameterless=[Depends(_check_qq_client)])
async def handle_pixiv(event: Event, illust_id: int) -> None:
    await send_as_forward(event, illust_id, PixivDownloader())
