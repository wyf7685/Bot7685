import contextlib
import pathlib
from collections.abc import AsyncGenerator

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


async def download_album(album_id: int) -> jmcomic.JmAlbumDetail:
    return await run_sync(jmcomic.new_downloader(option).download_album)(album_id)
