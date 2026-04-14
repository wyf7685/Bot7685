from collections.abc import AsyncIterable, Awaitable, Callable
from typing import NoReturn

import anyio
import httpx
import jmcomic
from nonebot import logger, require
from nonebot.adapters import Event
from nonebot.exception import ActionFailed, MatcherException
from nonebot.params import Depends
from nonebot.permission import SUPERUSER, User
from nonebot.plugin import PluginMetadata

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

require("src.service.cache")
require("src.plugins.trusted")
from src.plugins.trusted import TrustedUser

from .option import download_image, fetch_album_images, get_album_detail
from .utils import DownloadTask, abatched, format_exc_msg

__plugin_meta__ = PluginMetadata(
    name="jmcomic",
    description="jmcomic",
    usage="/jm <album_id: int>",
    supported_adapters={"~onebot.v11", "~milky"},
    type="application",
)


matcher = on_alconna(
    Alconna("jm", Args["album_id", int]),
    permission=TrustedUser(),
)


async def download_task(
    client: httpx.AsyncClient,
    task: DownloadTask,
    image: jmcomic.JmImageDetail,
) -> None:
    try:
        task.set_result(await download_image(client, image))
    except Exception as err:
        logger.opt(exception=err).warning(f"下载失败: {err}")
        task.set_result(None)


async def send_segs(
    uid: str,
    data: AsyncIterable[tuple[tuple[int, int], bytes | None]],
    start_soon: Callable[[Callable[[], Awaitable[object]]], object],
) -> None:
    async for batch in abatched(data, 20):
        nodes = [
            CustomNode(
                uid=uid,
                name=f"P_{p}_{i}",
                content=UniMessage.image(raw=raw)
                if raw is not None
                else UniMessage.text("[图片下载失败]"),
            )
            for (p, i), raw in batch
        ]
        st, ed = batch[0][0], batch[-1][0]
        logger.opt(colors=True).info(f"开始发送合并转发: <c>{st}</c> - <c>{ed}</c>")
        start_soon(UniMessage.reference(*nodes).send)


async def send_album_forward(
    uid: str,
    album: jmcomic.JmAlbumDetail,
    recall: Callable[[], object],
    concurrency: int = 10,
) -> None:
    pending = await fetch_album_images(album)
    running: list[tuple[tuple[int, int], DownloadTask]] = []

    def put_task() -> None:
        key, image = pending.pop(0)
        tg.start_soon(download_task, client, (task := DownloadTask()), image)
        running.append((key, task))

    async def iter_images() -> AsyncIterable[tuple[tuple[int, int], bytes | None]]:
        for _ in range(min(concurrency, len(pending))):
            put_task()

        while running:
            key, task = running.pop(0)
            yield (key, await task.wait())
            if pending:
                put_task()

    async def send_album_info() -> None:
        await UniMessage.text(
            f"ID: {album.id}\n"
            f"标题: {album.title}\n"
            f"作者: {album.author}\n"
            f"标签: {', '.join(album.tags)}\n"
            f"页数: {len(pending)}"
        ).send(reply_to=True)
        recall()

    async with (
        httpx.AsyncClient() as client,
        anyio.create_task_group() as tg,
    ):
        tg.start_soon(send_album_info)
        tg.start_soon(send_segs, uid, iter_images(), tg.start_soon)


async def _check_qq_client(target: MsgTarget) -> None:
    if target.scope != SupportScope.qq_client:
        matcher.skip()


@matcher.assign("album_id", parameterless=[Depends(_check_qq_client)])
async def handle_qq_client(event: Event, album_id: int) -> None:
    receipt = await UniMessage.text(f"开始 {album_id} 的下载任务…").send(reply_to=True)

    try:
        album = await get_album_detail(album_id)
    except jmcomic.JmcomicException as err:
        await UniMessage.text(f"获取信息失败:\n{err}").finish()
    except Exception as err:
        await UniMessage.text(f"获取信息失败: 未知错误\n{err!r}").finish()

    async def wait_for_terminate() -> None:
        permission = SUPERUSER | User.from_event(event, perm=matcher.permission)

        @waiter.waiter(
            [type(event)],
            keep_session=False,
            permission=permission,
            block=True,
        )
        def wait(e: Event) -> str:
            return e.get_message().extract_plain_text()

        words = {"terminate", "stop", "cancel", "中止", "停止", "取消"}
        async for msg in wait():
            if msg is not None and msg.strip() in words:
                await UniMessage.text(f"中止 {album_id} 的下载任务").finish(
                    reply_to=True
                )

    async def send_forward() -> None:
        try:
            await send_album_forward(
                event.get_user_id(), album, lambda: schedule_recall(receipt)
            )
        finally:
            tg.cancel_scope.cancel()

    async def handle_exc(exc_group: ExceptionGroup, msg: str) -> NoReturn:
        logger.opt(exception=exc_group).warning(msg)
        await UniMessage.text(format_exc_msg(msg, exc_group)).finish(reply_to=True)

    try:
        async with anyio.create_task_group() as tg:
            tg.start_soon(wait_for_terminate)
            tg.start_soon(send_forward)
    except* MatcherException:
        raise
    except* ActionFailed as exc_group:
        await handle_exc(exc_group, "发送失败")
    except* Exception as exc_group:
        await handle_exc(exc_group, "下载失败")
    else:
        await UniMessage.text(f"完成 {album_id} 的下载任务").finish(reply_to=True)
