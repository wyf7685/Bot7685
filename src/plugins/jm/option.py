import io
import math
from collections.abc import Iterable

import anyio
import httpx
import jmcomic
import PIL.Image
from nonebot.log import logger
from nonebot.utils import escape_tag, run_sync
from nonebot_plugin_localstore import get_plugin_cache_dir

from src.service.cache import cache_with, get_cache
from src.utils import with_semaphore

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


jmcomic.JmModuleConfig.EXECUTOR_LOG = jm_log  # pyright: ignore[reportAttributeAccessIssue]
option = jmcomic.JmOption.construct(OPTION)
photo_cache = get_cache[jmcomic.JmPhotoDetail]("jmcomic_option:photo", pickle=True)


@cache_with(
    int,
    namespace="jmcomic_option:album",
    key=lambda album_id: f"album_{album_id}",
    pickle=True,
)
async def get_album_detail(album_id: int) -> jmcomic.JmAlbumDetail:
    return await run_sync(option.new_jm_client().get_album_detail)(album_id)


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

    with io.BytesIO() as output:
        decoded.save(output, format="JPEG")
        return output.getvalue()


async def download_image(
    client: httpx.AsyncClient,
    image: jmcomic.JmImageDetail,
) -> bytes:
    num = jmcomic.JmImageTool.get_num_by_detail(image)
    url = image.download_url
    for try_count in range(5):
        try:
            response = (await client.get(url)).raise_for_status()
        except Exception as err:
            logger.opt(colors=True).warning(
                f"下载失败 [<y>{try_count + 1}</y>/<y>5</y>]:"
                f" <c>{url}</c> - <r>{escape_tag(repr(err))}</r>"
            )
            if try_count == 4:
                raise
            await anyio.sleep(0.5)
        else:
            return _decode_image(response.content, num)
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
