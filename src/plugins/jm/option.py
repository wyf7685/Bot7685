import io
import math

import anyio
import httpx
import jmcomic
import PIL.Image
from nonebot.log import logger
from nonebot.utils import escape_tag, run_sync
from nonebot_plugin_localstore import get_plugin_cache_dir

from src.plugins.cache import cache_with

logger = logger.opt(colors=True)


def jm_log(topic: str, msg: str) -> None:
    logger.info(f"[<m>{topic}</m>] {escape_tag(msg)}")


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


@cache_with(
    int,
    namespace="jmcomic_option:album",
    key=lambda album_id: f"album_{album_id}",
    pickle=True,
)
async def get_album_detail(album_id: int) -> jmcomic.JmAlbumDetail:
    return await run_sync(option.new_jm_client().get_album_detail)(album_id)


@cache_with(
    jmcomic.JmPhotoDetail,
    namespace="jmcomic_option:photo",
    key=lambda photo: f"photo_{photo.photo_id}",
    pickle=True,
)
async def check_photo(photo: jmcomic.JmPhotoDetail) -> jmcomic.JmPhotoDetail:
    await run_sync(option.new_jm_client().check_photo)(photo)
    return photo


async def download_album(album_id: int) -> jmcomic.JmAlbumDetail:
    return await run_sync(jmcomic.new_downloader(option).download_album)(album_id)


def decode_image(raw: bytes, num: int) -> bytes:
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


async def download_image(image: jmcomic.JmImageDetail) -> bytes:
    num = jmcomic.JmImageTool.get_num_by_detail(image)
    url = image.download_url
    async with httpx.AsyncClient() as client:
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
                return decode_image(response.content, num)
        raise RuntimeError("下载失败")
