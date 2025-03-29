import asyncio
import contextlib
import io
import math
import pathlib
from collections.abc import AsyncGenerator

import httpx
import PIL.Image
from nonebot.log import logger
from nonebot.utils import escape_tag, run_sync
from nonebot_plugin_localstore import get_plugin_cache_dir

import jmcomic

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
OPTION_PDF = OPTION | {
    "plugins": {
        "after_album": [
            {
                "plugin": "img2pdf",
                "kwargs": {
                    "pdf_dir": str(PDF_DIR),
                    "filename_rule": "Aalbum_id",
                },
            }
        ],
    },
}

jmcomic.JmModuleConfig.EXECUTOR_LOG = jm_log  # pyright: ignore[reportAttributeAccessIssue]
option = jmcomic.JmOption.construct(OPTION)
option_pdf = jmcomic.JmOption.construct(OPTION_PDF)


@contextlib.asynccontextmanager
async def download_album_pdf(album_id: int) -> AsyncGenerator[pathlib.Path]:
    downloader = jmcomic.new_downloader(option_pdf)
    detail = await run_sync(downloader.download_album)(album_id)
    pdf_file = PDF_DIR / f"{detail.album_id}.pdf"
    try:
        yield pdf_file
    finally:
        pdf_file.unlink()


async def get_album_detail(album_id: int) -> jmcomic.JmAlbumDetail:
    return await run_sync(option.new_jm_client().get_album_detail)(album_id)


async def check_photo(photo: jmcomic.JmPhotoDetail) -> jmcomic.JmPhotoDetail:
    await run_sync(option.new_jm_client().check_photo)(photo)
    return photo


async def download_album(album_id: int) -> jmcomic.JmAlbumDetail:
    return await run_sync(jmcomic.new_downloader(option).download_album)(album_id)


def decode_image(raw: bytes, num: int) -> bytes:
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
    num = jmcomic.JmImageTool.get_num_by_url(image.scramble_id, image.download_url)
    async with httpx.AsyncClient() as client:
        for try_count in range(5):
            try:
                response = (await client.get(image.download_url)).raise_for_status()
            except Exception as err:
                logger.warning(f"下载失败：{err}，尝试重试 {try_count + 1} 次")
                if try_count == 4:
                    raise
                await asyncio.sleep(0.5)
            else:
                return decode_image(response.content, num)
        raise RuntimeError("下载失败")
