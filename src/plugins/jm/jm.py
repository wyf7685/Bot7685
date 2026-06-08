import io
import math
from collections.abc import AsyncGenerator, Iterable
from typing import override

import anyio
import httpx
import jmcomic
import PIL.Image
from nonebot.log import logger
from nonebot.utils import escape_tag, run_sync
from nonebot_plugin_localstore import get_plugin_cache_dir

from src.service.cache import get_cache
from src.utils import with_semaphore

from .common import Downloader
from .utils import generate_random_ascii_string

logger = logger.opt(colors=True)


def jm_log(topic: str, msg: str, exc: Exception | None = None) -> None:
    log = logger.info if exc is None else logger.opt(exception=exc).warning
    log(f"[<m>{topic}</m>] {escape_tag(str(msg))}")


CACHE_DIR = get_plugin_cache_dir()
DOWNLOAD_DIR = CACHE_DIR / "download"
PDF_DIR = CACHE_DIR / "pdf"
OPTION = {
    "version": "2.1",
    "dir_rule": {"base_dir": str(DOWNLOAD_DIR), "rule": "Bd_Pid"},
    "download": {"threading": {"image": 4, "photo": 4}},
}


jmcomic.JmModuleConfig.EXECUTOR_LOG = jm_log  # pyright: ignore[reportAttributeAccessIssue]  # ty:ignore[invalid-assignment]
option = jmcomic.JmOption.construct(OPTION)
album_cache = get_cache("jmcomic_option:album", jmcomic.JmAlbumDetail, mode="pickle")
photo_cache = get_cache("jmcomic_option:photo", jmcomic.JmPhotoDetail, mode="pickle")


async def get_album_detail(album_id: int) -> jmcomic.JmAlbumDetail:
    if cached := await album_cache.get(f"album_{album_id}"):
        return cached
    detail = await run_sync(option.new_jm_client().get_album_detail)(album_id)
    await album_cache.set(f"album_{album_id}", detail)
    return detail


def _decode_image(raw: bytes, num: int) -> bytes:
    if not num:
        return raw

    img = PIL.Image.open(io.BytesIO(raw))
    decoded = PIL.Image.new("RGB", img.size)

    w, h = img.size
    over = h % num
    for i in range(num):
        move = math.floor(h / num)
        y_src = h - (move * (i + 1)) - over
        y_dst = move * i

        if i == 0:
            move += over
        else:
            y_dst += over

        decoded.paste(
            img.crop((0, y_src, w, y_src + move)),
            (0, y_dst, w, y_dst + move),
        )

    decoded.info["comment"] = generate_random_ascii_string(16)
    with io.BytesIO() as output:
        decoded.save(output, format="JPEG")
        return output.getvalue()


async def download_image(
    client: httpx.AsyncClient,
    image: jmcomic.JmImageDetail,
) -> bytes:
    num = jmcomic.JmImageTool.get_num_by_detail(image)
    url = image.download_url
    for attempt in range(5):
        try:
            response = (await client.get(url)).raise_for_status()
            return _decode_image(response.content, num)
        except Exception as exc:
            logger.opt(colors=True).warning(
                f"下载失败 [<y>{attempt + 1}</y>/<y>5</y>]:"
                f" <c>{escape_tag(url)}</c> - <r>{escape_tag(repr(exc))}</r>"
            )
            if attempt == 4:
                raise
            await anyio.sleep(0.5)
    raise RuntimeError("下载失败")


async def check_album(
    album: jmcomic.JmAlbumDetail,
) -> Iterable[tuple[int, jmcomic.JmPhotoDetail]]:
    check_photo = run_sync(option.new_jm_client().check_photo)

    @with_semaphore(8)
    async def check(p: int, photo: jmcomic.JmPhotoDetail) -> None:
        try:
            if (cache := await photo_cache.get(photo.photo_id)) is not None:
                checked[p] = cache
            else:
                await check_photo(photo)
                await photo_cache.set(photo.photo_id, photo)
                checked[p] = photo
        except Exception as err:
            logger.opt(colors=True, exception=err).warning(
                f"检查失败: <y>{p}</y> - <c>{escape_tag(repr(photo))}</c>"
            )

    checked: dict[int, jmcomic.JmPhotoDetail] = {}
    async with anyio.create_task_group() as tg:
        for p, photo in enumerate(album, 1):
            tg.start_soon(check, p, photo)

    return sorted(checked.items(), key=lambda x: x[0])


async def fetch_album_images(
    album: jmcomic.JmAlbumDetail,
) -> list[tuple[tuple[int, int], jmcomic.JmImageDetail]]:
    return [
        ((p, i), image)
        for p, photo in await check_album(album)
        for i, image in enumerate(photo, 1)
    ]


class JmDownloader(Downloader[jmcomic.JmAlbumDetail, jmcomic.JmImageDetail]):
    @override
    def create_httpx_client(self) -> httpx.AsyncClient:
        transport = httpx.AsyncHTTPTransport(retries=3, http2=True)
        return httpx.AsyncClient(transport=transport)

    @override
    async def fetch_index(self, album_id: int) -> jmcomic.JmAlbumDetail:
        return await get_album_detail(album_id)

    @override
    async def format_summary(self, album: jmcomic.JmAlbumDetail) -> str:
        images = await fetch_album_images(album)
        return (
            f"ID: {album.album_id}\n"
            f"标题: {album.title}\n"
            f"作者: {album.author}\n"
            f"标签: {', '.join(album.tags)}\n"
            f"页数: {len(images)}"
        )

    @override
    async def generate_task(
        self, album: jmcomic.JmAlbumDetail
    ) -> AsyncGenerator[tuple[str, jmcomic.JmImageDetail]]:
        for (p, i), image in await fetch_album_images(album):
            yield f"P_{p}_{i}", image

    async def execute_task(self, task: jmcomic.JmImageDetail) -> bytes:
        return await download_image(await self.get_httpx_client(), task)
