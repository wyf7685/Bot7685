import functools
from collections.abc import AsyncGenerator, AsyncIterable, Awaitable, Callable
from typing import NoReturn

import anyio
import jmcomic
from nonebot import logger, require
from nonebot.adapters import milky, telegram
from nonebot.adapters.onebot import v11 as ob11
from nonebot.exception import ActionFailed, MatcherException
from nonebot.permission import SUPERUSER, User
from nonebot.plugin import PluginMetadata

from src.utils import ignore_exc

require("nonebot_plugin_alconna")
require("nonebot_plugin_localstore")
require("nonebot_plugin_waiter")
from nonebot_plugin_alconna import Alconna, Args, CustomNode, UniMessage, on_alconna
from nonebot_plugin_waiter import waiter

require("src.plugins.trusted")
from src.plugins.trusted import TrustedUser

from .option import download_image, fetch_album_images, get_album_detail
from .utils import Task, abatched, format_exc_msg

__plugin_meta__ = PluginMetadata(
    name="jmcomic",
    description="jmcomic",
    usage="/jm <album_id: int>",
    supported_adapters={"~onebot.v11", "~milky", "~telegram"},
    type="application",
)


matcher = on_alconna(
    Alconna("jm", Args["album_id", int]),
    permission=TrustedUser(),
)


async def download_task(task: Task[bytes | None], image: jmcomic.JmImageDetail) -> None:
    try:
        task.set_result(await download_image(image))
    except Exception as err:
        logger.opt(exception=err).warning(f"下载失败: {err}")
        task.set_result(None)


async def send_segs(
    data: AsyncIterable[tuple[tuple[int, int], bytes | None]],
    start_soon: Callable[[Callable[[], Awaitable[object]]], object],
) -> None:
    async for batch in abatched(data, 20):
        nodes = [
            CustomNode(
                uid="10086",
                name=f"P_{p}_{i}",
                content=UniMessage.image(raw=raw)
                if raw is not None
                else "[图片下载失败]",
            )
            for (p, i), raw in batch
        ]
        st, ed = batch[0][0], batch[-1][0]
        logger.opt(colors=True).info(f"开始发送合并转发: <c>{st}</c> - <c>{ed}</c>")
        start_soon(UniMessage.reference(*nodes).send)


async def send_album_forward(
    album: jmcomic.JmAlbumDetail,
    recall: Callable[[], Awaitable[object]],
    batch_size: int = 8,
) -> None:
    pending = await fetch_album_images(album)
    running: list[tuple[tuple[int, int], Task[bytes | None]]] = []

    def put_task() -> None:
        key, image = pending.pop(0)
        task: Task[bytes | None] = Task()
        tg.start_soon(download_task, task, image)
        running.append((key, task))

    async def iter_images() -> AsyncGenerator[tuple[tuple[int, int], bytes | None]]:
        for _ in range(min(batch_size, len(pending))):
            put_task()

        while running:
            key, task = running.pop(0)
            yield (key, await task.wait())
            if pending:
                put_task()

    msg = UniMessage.text(
        f"ID: {album.id}\n"
        f"标题: {album.title}\n"
        f"作者: {album.author}\n"
        f"标签: {', '.join(album.tags)}\n"
        f"页数: {len(pending)}"
    )
    async with anyio.create_task_group() as tg:
        tg.start_soon(recall)
        tg.start_soon(functools.partial(msg.send, reply_to=True))
        tg.start_soon(send_segs, iter_images(), tg.start_soon)


@matcher.assign("album_id")
async def handle_ob11_milky(
    event: ob11.MessageEvent | milky.MessageEvent,
    album_id: int,
) -> None:
    receipt = await UniMessage(f"开始 {album_id} 的下载任务...").send(reply_to=True)

    try:
        album = await get_album_detail(album_id)
    except jmcomic.JmcomicException as err:
        await UniMessage(f"获取信息失败:\n{err}").finish()
    except Exception as err:
        await UniMessage(f"获取信息失败: 未知错误\n{err!r}").finish()

    async def wait_for_terminate() -> None:
        permission = SUPERUSER | User.from_event(event, perm=matcher.permission)

        @waiter([event.get_type()], permission=permission)
        def wait(e: ob11.MessageEvent | milky.MessageEvent) -> str:
            return e.get_message().extract_plain_text()

        words = {"terminate", "stop", "cancel", "中止", "停止", "取消"}
        async for msg in wait():
            if msg is not None and msg.strip() in words:
                await UniMessage(f"中止 {album_id} 的下载任务").finish(reply_to=True)

    @ignore_exc
    async def recall() -> None:
        if receipt.recallable:
            await receipt.recall()

    async def send_forward() -> None:
        try:
            await send_album_forward(album, recall)
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


@matcher.assign("album_id")
async def handle_telegram(_: telegram.Bot, album_id: int) -> None:
    try:
        album = await get_album_detail(album_id)
    except jmcomic.JmcomicException as exc:
        await UniMessage.text(format_exc_msg("获取信息失败", exc)).finish(reply_to=True)
    except Exception as exc:
        await UniMessage.text(
            format_exc_msg("获取信息失败: 未知错误", exc),
        ).finish(reply_to=True)

    msg = UniMessage.text(
        f"ID: {album.id}\n"
        f"标题: {album.title}\n"
        f"作者: {album.author}\n"
        f"标签: {', '.join(album.tags)}\n"
    )

    try:
        images = await fetch_album_images(album)
    except jmcomic.JmcomicException as exc:
        await (
            msg.text("\n")
            .text(format_exc_msg("获取图片信息失败", exc))
            .finish(reply_to=True)
        )
    except Exception as exc:
        await (
            msg.text("\n")
            .text(format_exc_msg("获取图片信息失败: 未知错误", exc))
            .finish(reply_to=True)
        )
    else:
        await msg.text(f"页数: {len(images)}").finish(reply_to=True)
