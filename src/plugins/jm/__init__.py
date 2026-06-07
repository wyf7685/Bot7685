import contextlib
from collections import deque
from collections.abc import AsyncGenerator, Iterable
from typing import Literal, NoReturn

import anyio
import httpx
import jmcomic
from nonebot import logger, require
from nonebot.adapters import Event
from nonebot.exception import ActionFailed, MatcherException, NetworkError
from nonebot.params import Depends
from nonebot.permission import SUPERUSER, User
from nonebot.plugin import PluginMetadata, inherit_supported_adapters
from nonebot.utils import escape_tag

from src.utils import schedule_recall

require("nonebot_plugin_alconna")
require("nonebot_plugin_localstore")
require("nonebot_plugin_waiter")
import nonebot_plugin_waiter.unimsg as waiter
from nonebot_plugin_alconna import (
    Alconna,
    Args,
    CustomNode,
    MsgTarget,
    SupportScope,
    UniMessage,
    on_alconna,
)
from nonebot_plugin_alconna.uniseg import Receipt

require("src.service.cache")
require("src.plugins.trusted")
from src.plugins.trusted import TrustedUser

from .option import download_image, fetch_album_images, get_album_detail
from .utils import DownloadTask, abatched, format_exc_msg

__plugin_meta__ = PluginMetadata(
    name="jmcomic",
    description="jmcomic",
    usage="/jm <album_id: int>",
    supported_adapters=inherit_supported_adapters("nonebot_plugin_alconna"),
    type="application",
)


matcher = on_alconna(
    Alconna("jm", Args["album_id", int]),
    permission=TrustedUser(),
)

SEG_BATCH_SIZE = 20


async def iter_images[K](
    images: Iterable[tuple[K, jmcomic.JmImageDetail]],
    concurrency: int,
) -> AsyncGenerator[tuple[K, bytes | str]]:
    pending = list(images)
    running: deque[tuple[K, DownloadTask]] = deque()

    async def download(
        task: DownloadTask,
        image: jmcomic.JmImageDetail,
    ) -> None:
        try:
            raw = await download_image(client, image)
            task.set_result(raw)
        except Exception as exc:
            logger.opt(colors=True, exception=exc).warning(
                f"下载失败: <i><c>{escape_tag(image.img_url)}</></>"
            )
            task.set_result(repr(exc))

    def put_task() -> None:
        key, image = pending.pop(0)
        tg.start_soon(download, (task := DownloadTask()), image)
        running.append((key, task))

    transport = httpx.AsyncHTTPTransport(retries=3, http2=True)
    async with (
        httpx.AsyncClient(transport=transport) as client,
        anyio.create_task_group() as tg,
    ):
        for _ in range(min(concurrency, len(pending))):
            put_task()

        while running:
            key, task = running.popleft()
            yield (key, await task)
            if pending:
                put_task()


async def send_nodes(nodes: list[CustomNode]) -> None:
    try:
        await UniMessage.reference(*nodes).send()
    except NetworkError as exc:
        logger.warning(f"发送合并转发时发生网络错误: {exc!r}")


async def send_album_info(album: jmcomic.JmAlbumDetail, page_count: int) -> None:
    await UniMessage.text(
        f"ID: {album.id}\n"
        f"标题: {album.title}\n"
        f"作者: {album.author}\n"
        f"标签: {', '.join(album.tags)}\n"
        f"页数: {page_count}"
    ).send(reply_to=True)


async def send_album_forward(
    uid: str,
    album: jmcomic.JmAlbumDetail,
    receipt: Receipt,
    concurrency: int = 10,
) -> None:
    pending = await fetch_album_images(album)

    await send_album_info(album, len(pending))
    schedule_recall(receipt)

    async with (
        contextlib.aclosing(iter_images(pending, concurrency)) as agen,
        anyio.create_task_group() as tg,
    ):
        async for batch in abatched(agen, SEG_BATCH_SIZE):
            nodes = [
                CustomNode(
                    uid=uid,
                    name=f"P_{p}_{i}",
                    content=UniMessage.image(raw=raw)
                    if isinstance(raw, bytes)
                    else UniMessage.text(f"[图片下载失败: {raw}]"),
                )
                for (p, i), raw in batch
            ]
            st, ed = batch[0][0], batch[-1][0]
            logger.opt(colors=True).info(f"开始发送合并转发: <c>{st}</c> - <c>{ed}</c>")
            tg.start_soon(send_nodes, nodes)


async def _check_qq_client(target: MsgTarget) -> None:
    if target.scope != SupportScope.qq_client:
        logger.warning(f"不支持的消息目标: {target.scope}")
        matcher.skip()


async def wait_for_terminate(event: Event, album_id: int) -> None:
    words = {"terminate", "stop", "cancel", "中止", "停止", "取消"}

    def waiter_rule(e: Event) -> bool:
        return e.get_message().extract_plain_text().strip() in words

    @waiter.waiter(
        [type(event)],
        keep_session=False,
        rule=waiter_rule,
        permission=SUPERUSER | User.from_event(event, perm=matcher.permission),
        block=True,
    )
    def wait() -> Literal[True]:
        return True

    while True:
        if await wait.wait():
            await UniMessage.text(f"中止 {album_id} 的下载任务").finish(reply_to=True)


@matcher.assign("album_id", parameterless=[Depends(_check_qq_client)])
async def handle_qq_client(event: Event, album_id: int) -> None:
    receipt = await UniMessage.text(f"开始 {album_id} 的下载任务…").send(reply_to=True)

    try:
        album = await get_album_detail(album_id)
    except jmcomic.JmcomicException as err:
        await UniMessage.text(f"获取信息失败:\n{err}").finish()
    except Exception as err:
        await UniMessage.text(f"获取信息失败: 未知错误\n{err!r}").finish()

    async def send_forward() -> None:
        try:
            await send_album_forward(event.get_user_id(), album, receipt)
        finally:
            tg.cancel_scope.cancel()

    async def handle_exc(exc_group: ExceptionGroup, msg: str) -> NoReturn:
        logger.opt(exception=exc_group).warning(msg)
        await UniMessage.text(format_exc_msg(msg, exc_group)).finish(reply_to=True)

    try:
        async with anyio.create_task_group() as tg:
            tg.start_soon(wait_for_terminate, event, album_id)
            await send_forward()
    except* MatcherException:
        raise
    except* (ActionFailed, NetworkError) as exc_group:
        await handle_exc(exc_group, "发送失败")
    except* Exception as exc_group:
        await handle_exc(exc_group, "下载失败")
    else:
        await UniMessage.text(f"完成 {album_id} 的下载任务").finish(reply_to=True)
