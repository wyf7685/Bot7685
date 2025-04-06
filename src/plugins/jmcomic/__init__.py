import functools
from collections.abc import AsyncGenerator, Awaitable, Callable
from typing import Annotated

import anyio
from nonebot import logger, require
from nonebot.adapters.onebot import v11
from nonebot.adapters.onebot.v11 import Message as V11Msg
from nonebot.adapters.onebot.v11 import MessageSegment as V11Seg
from nonebot.exception import MatcherException
from nonebot.params import Depends
from nonebot.permission import SUPERUSER, User
from nonebot.plugin import PluginMetadata
from nonebot.utils import escape_tag

import jmcomic

require("nonebot_plugin_alconna")
require("nonebot_plugin_localstore")
require("nonebot_plugin_waiter")
from nonebot_plugin_alconna import Alconna, Args, UniMessage, on_alconna
from nonebot_plugin_waiter import waiter

require("src.plugins.trusted")
from src.plugins.trusted import TrustedUser

from .jm_option import check_photo, download_album_pdf, download_image, get_album_detail
from .utils import abatched, flatten_exception_group

__plugin_meta__ = PluginMetadata(
    name="jmcomic",
    description="jmcomic",
    usage="/jm <id:int>",
)


matcher = on_alconna(
    Alconna("jm", Args["album_id", int]),
    permission=TrustedUser(),
)


async def check_lagrange(bot: v11.Bot) -> None:
    info = await bot.get_version_info()
    app_name: str = info.get("app_name", "unknown")
    if "lagrange" not in app_name.lower():
        matcher.skip()


type SendFunc = Callable[[list[V11Seg]], Awaitable[object]]


def send_func(bot: v11.Bot, event: v11.MessageEvent) -> SendFunc:
    # fmt: off
    return (
        (lambda m: bot.send_group_forward_msg(group_id=event.group_id, messages=m))
        if isinstance(event, v11.GroupMessageEvent) else
        (lambda m: bot.send_private_forward_msg(user_id=event.user_id, messages=m))
    )


class Task[T]:
    event: anyio.Event
    result: T  # pyright: ignore[reportUninitializedInstanceVariable]

    def __init__(self) -> None:
        self.event = anyio.Event()

    def set_result(self, value: T) -> None:
        self.result = value
        self.event.set()

    async def wait(self) -> T:
        await self.event.wait()
        return self.result


async def check_album(
    album: jmcomic.JmAlbumDetail,
) -> list[tuple[int, jmcomic.JmPhotoDetail]]:
    async def check(p: int, photo: jmcomic.JmPhotoDetail) -> None:
        try:
            async with sem:
                checked[p] = await check_photo(photo)
        except Exception as err:
            logger.opt(colors=True, exception=err).warning(
                f"检查失败: <y>{p}</y> - <c>{escape_tag(repr(photo))}</c>"
            )

    checked: dict[int, jmcomic.JmPhotoDetail] = {}
    async with (
        anyio.create_task_group() as tg,
        anyio.Semaphore(9) as sem,
    ):
        for p, photo in enumerate(album, 1):
            tg.start_soon(check, p, photo)

    return sorted(checked.items(), key=lambda x: x[0])


async def send_album_forward(
    album: jmcomic.JmAlbumDetail,
    send: SendFunc,
    batch_size: int,
) -> None:
    pending = [
        ((p, i), image)
        for p, photo in await check_album(album)
        for i, image in enumerate(photo, 1)
    ]

    async def download(task: Task[bytes | None], image: jmcomic.JmImageDetail) -> None:
        try:
            task.set_result(await download_image(image))
        except Exception as err:
            logger.opt(exception=err).warning(f"下载失败: {err}")
            task.set_result(None)

    async def iter_images() -> AsyncGenerator[tuple[tuple[int, int], bytes | None]]:
        running: list[tuple[tuple[int, int], Task[bytes | None]]] = []

        def put_one() -> None:
            key, image = pending.pop(0)
            tg.start_soon(download, task := Task[bytes | None](), image)
            running.append((key, task))

        for _ in range(min(batch_size, len(pending))):
            put_one()

        while running:
            key, task = running.pop(0)
            yield (key, await task.wait())
            if pending:
                put_one()

    async def send_segs() -> None:
        async for batch in abatched(iter_images(), 20):
            segs = [
                V11Seg.node_custom(
                    user_id=10086,
                    nickname=f"P_{p}_{i}",
                    content=V11Msg(V11Seg.image(raw))
                    if raw is not None
                    else "图片下载失败",
                )
                for (p, i), raw in batch
            ]
            logger.opt(colors=True).info(
                f"开始发送合并转发: <c>{batch[0][0]}</c> - <c>{batch[-1][0]}</c>"
            )
            tg.start_soon(send, segs)

    msg = UniMessage.text(
        f"ID: {album.id}\n"
        f"标题: {album.title}\n"
        f"作者: {album.author}\n"
        f"标签: {', '.join(album.tags)}\n"
        f"页数: {len(pending)}"
    )
    async with anyio.create_task_group() as tg:
        tg.start_soon(functools.partial(msg.send, reply_to=True))
        tg.start_soon(send_segs)


@matcher.assign("album_id", parameterless=[Depends(check_lagrange)])
async def _(
    event: v11.MessageEvent,
    album_id: int,
    send: Annotated[SendFunc, Depends(send_func)],
) -> None:
    await UniMessage(f"开始 {album_id} 的下载任务...").send(reply_to=True)

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

    async def send_forward() -> None:
        try:
            await send_album_forward(album, send, 8)
        finally:
            tg.cancel_scope.cancel()

    try:
        async with anyio.create_task_group() as tg:
            tg.start_soon(wait_for_terminate)
            tg.start_soon(send_forward)
    except* MatcherException:
        raise
    except* Exception as exc_group:
        logger.opt(exception=exc_group).warning("下载失败")
        await UniMessage(
            "下载失败:\n"
            + "\n".join(
                (str if isinstance(exc, jmcomic.JmcomicException) else repr)(exc)
                for exc in flatten_exception_group(exc_group)
            )
        ).finish(reply_to=True)
    else:
        await UniMessage(f"完成 {album_id} 的下载任务").finish(reply_to=True)


@matcher.assign("album_id")
async def _(album_id: int) -> None:
    async with download_album_pdf(album_id) as pdf_file:
        await UniMessage.file(path=pdf_file).finish()
