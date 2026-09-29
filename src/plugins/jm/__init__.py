from typing import Literal

import anyio
import nonebot_plugin_waiter.unimsg as waiter
from nonebot import logger
from nonebot.adapters import Event
from nonebot.exception import ActionFailed, MatcherException, NetworkError
from nonebot.matcher import Matcher, current_matcher
from nonebot.params import Depends
from nonebot.permission import SUPERUSER, User
from nonebot.plugin import PluginMetadata, inherit_supported_adapters
from nonebot_plugin_alconna import (
    Alconna,
    Args,
    Arparma,
    MsgTarget,
    Option,
    SupportScope,
    UniMessage,
    on_alconna,
)

from src.plugins.trusted import TrustedUser
from src.service.interaction import InteractionBusy, SessionGuard

from .common import Downloader
from .jm import JmDownloader
from .pixiv import PixivDownloader, construct_login_url, pixiv_auth
from .utils import format_exc_msg

__plugin_meta__ = PluginMetadata(
    name="jmcomic",
    description="查询 JM 和 Pixiv 作品信息；追加 get 下载并发送图片",
    usage="jm <album_id: int> [get]\ngetpixiv <illust_id: int> [get]\npixivlogin",
    supported_adapters=inherit_supported_adapters("nonebot_plugin_alconna"),
    type="application",
)


cmd_jm = on_alconna(
    Alconna("jm", Args["album_id", int], Option("get")),
    permission=TrustedUser(),
)
cmd_pixiv = on_alconna(
    Alconna("getpixiv", Args["illust_id", int], Option("get")),
    permission=TrustedUser(),
)
cmd_pixiv_login = on_alconna(
    Alconna("pixivlogin"),
    permission=SUPERUSER,
    use_cmd_start=True,
    block=True,
)
_login_guard = SessionGuard()


@cmd_pixiv_login.handle()
async def handle_pixiv_login(target: MsgTarget) -> None:
    if not target.private:
        await UniMessage.text("请在私聊中登录 Pixiv，避免授权码泄漏。").finish()
    try:
        async with _login_guard.acquire():
            url, verifier = construct_login_url()
            reply = await waiter.prompt(
                f"打开以下链接登录 Pixiv，并在 5 分钟内回复授权码：\n{url}",
                timeout=300,
            )
            if reply is None:
                await UniMessage.text("Pixiv 登录超时。").finish()
            code = reply.extract_plain_text().strip()
            if not code or code.casefold() in {"cancel", "取消"}:
                await UniMessage.text("已取消 Pixiv 登录。").finish()
            try:
                await pixiv_auth.login(code, verifier)
            except Exception as exc:
                logger.error(f"Pixiv 登录失败: {type(exc).__name__}")
                await UniMessage.text("Pixiv 登录失败，原凭据保持不变。").finish()
            await UniMessage.text("Pixiv 登录成功。").finish()
    except InteractionBusy:
        await UniMessage.text("已有 Pixiv 登录会话正在进行，请稍后重试。").finish()


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
        permission=SUPERUSER
        | User.from_event(event, perm=current_matcher.get().permission),
        block=True,
    )
    def wait() -> Literal[True]:
        return True

    while True:
        if await wait.wait():
            await UniMessage.text(f"中止 {id} 的下载任务").finish(reply_to=True)


async def send_forward(event: Event, id: int, downloader: Downloader) -> None:
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


async def send_summary[I, T](id: int, downloader: Downloader[I, T]) -> None:
    try:
        index = await downloader.fetch_index(id)
    except Exception as err:
        await UniMessage.text(f"获取信息失败: 未知错误\n{err!r}").finish(reply_to=True)

    await UniMessage.text(await downloader.format_summary(index)).finish(reply_to=True)


@cmd_jm.assign("album_id", parameterless=[Depends(_check_qq_client)])
async def handle_jm(event: Event, album_id: int, arp: Arparma) -> None:
    downloader = JmDownloader()
    if arp.find("get"):
        await send_forward(event, album_id, downloader)
    else:
        await send_summary(album_id, downloader)


@cmd_pixiv.assign("illust_id", parameterless=[Depends(_check_qq_client)])
async def handle_pixiv(event: Event, illust_id: int, arp: Arparma) -> None:
    downloader = PixivDownloader()
    if arp.find("get"):
        await send_forward(event, illust_id, downloader)
    else:
        await send_summary(illust_id, downloader)
