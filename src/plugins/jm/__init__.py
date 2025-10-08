import contextlib
import functools
from collections.abc import AsyncGenerator, AsyncIterable, Awaitable, Callable
from typing import TYPE_CHECKING, Annotated, NoReturn

import anyio
import jmcomic
from nonebot import logger, require
from nonebot.adapters.onebot import v11
from nonebot.adapters.onebot.v11 import Message as V11Msg
from nonebot.adapters.onebot.v11 import MessageSegment as V11Seg
from nonebot.exception import ActionFailed, MatcherException
from nonebot.params import Depends
from nonebot.permission import SUPERUSER, User
from nonebot.plugin import PluginMetadata

require("nonebot_plugin_alconna")
require("nonebot_plugin_localstore")
require("nonebot_plugin_waiter")
from nonebot_plugin_alconna import Alconna, Args, UniMessage, on_alconna
from nonebot_plugin_waiter import waiter

require("src.plugins.trusted")
from src.plugins.trusted import TrustedUser

from .option import download_image, fetch_album_images, get_album_detail
from .utils import Task, abatched, format_exc, format_exc_msg, queued

if TYPE_CHECKING:
    from nonebot.adapters import telegram

__plugin_meta__ = PluginMetadata(
    name="jmcomic",
    description="jmcomic",
    usage="/jm <id:int>",
)


matcher = on_alconna(
    Alconna("jm", Args["album_id", int]),
    permission=TrustedUser(),
)


type SendFunc = Callable[[list[V11Seg]], Awaitable[None]]


def send_func(bot: v11.Bot, event: v11.MessageEvent) -> SendFunc:
    if isinstance(event, v11.GroupMessageEvent):
        api, params = "send_group_forward_msg", {"group_id": event.group_id}
    else:
        api, params = "send_private_msg", {"user_id": event.user_id}

    @queued
    async def send(m: list[V11Seg]) -> None:
        max_retry = 3

        for retry in range(max_retry):
            try:
                await bot.call_api(api, **params, messages=m, _timeout=60)
            except v11.NetworkError:
                return
            except Exception as exc:
                if retry == 2:
                    logger.error(f"发送合并转发失败 ({max_retry}/{max_retry})")
                    raise
                logger.opt(exception=exc).warning(
                    f"发送合并转发失败, 重试中... ({retry + 1}/{max_retry})"
                )
            else:
                return

    return send


async def download_task(task: Task[bytes | None], image: jmcomic.JmImageDetail) -> None:
    try:
        task.set_result(await download_image(image))
    except Exception as err:
        logger.opt(exception=err).warning(f"下载失败: {err}")
        task.set_result(None)


async def send_segs(
    data: AsyncIterable[tuple[tuple[int, int], bytes | None]],
    send: Callable[[list[V11Seg]], object],
) -> None:
    async for batch in abatched(data, 20):
        segs = [
            V11Seg.node_custom(
                user_id=10086,
                nickname=f"P_{p}_{i}",
                content=V11Msg(V11Seg.image(raw))
                if raw is not None
                else "[图片下载失败]",
            )
            for (p, i), raw in batch
        ]
        st, ed = batch[0][0], batch[-1][0]
        logger.opt(colors=True).info(f"开始发送合并转发: <c>{st}</c> - <c>{ed}</c>")
        send(segs)


async def send_album_forward(
    album: jmcomic.JmAlbumDetail,
    send: SendFunc,
    recall: Callable[[], Awaitable[object]],
    batch_size: int = 8,
) -> None:
    pending = await fetch_album_images(album)
    running: list[tuple[tuple[int, int], Task[bytes | None]]] = []

    def put() -> None:
        key, image = pending.pop(0)
        tg.start_soon(download_task, task := Task[bytes | None](), image)
        running.append((key, task))

    async def iter_images() -> AsyncGenerator[tuple[tuple[int, int], bytes | None]]:
        for _ in range(min(batch_size, len(pending))):
            put()

        while running:
            key, task = running.pop(0)
            yield (key, await task.wait())
            if pending:
                put()

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
        tg.start_soon(send_segs, iter_images(), functools.partial(tg.start_soon, send))


async def check_lagrange(bot: v11.Bot) -> None:
    info = await bot.get_version_info()
    app_name: str = info.get("app_name", "unknown")
    if "lagrange" not in app_name.lower():
        matcher.skip()


@matcher.assign("album_id", parameterless=[Depends(check_lagrange)])
async def handle_lagrange(
    event: v11.MessageEvent,
    album_id: int,
    send: Annotated[SendFunc, Depends(send_func)],
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
        def wait(e: v11.MessageEvent) -> str:
            return e.get_message().extract_plain_text()

        words = {"terminate", "stop", "cancel", "中止", "停止", "取消"}
        async for msg in wait():
            if msg is not None and msg.strip() in words:
                await UniMessage(f"中止 {album_id} 的下载任务").finish(reply_to=True)

    async def recall() -> None:
        if receipt.recallable:
            with contextlib.suppress(ActionFailed):
                await receipt.recall()

    async def send_forward() -> None:
        try:
            await send_album_forward(album, send, recall)
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
        await UniMessage(f"完成 {album_id} 的下载任务").finish(reply_to=True)


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
        await msg.text(f"\n获取图片信息失败:\n{format_exc(exc)}").finish(reply_to=True)
    except Exception as exc:
        await msg.text(
            f"\n获取图片信息失败: 未知错误\n{format_exc(exc)}",
        ).finish(reply_to=True)
    else:
        await msg.text(f"页数: {len(images)}").finish(reply_to=True)
