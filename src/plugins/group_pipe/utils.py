from typing import NamedTuple

import anyio
import fleep
import httpx
from nonebot_plugin_localstore import get_plugin_cache_dir


async def download_url(url: str) -> bytes:
    async with httpx.AsyncClient() as client:
        try:
            resp = await client.get(url)
            resp.raise_for_status()
        except (httpx.ConnectError, httpx.HTTPError):
            return b""
        else:
            return resp.read()


async def check_url_ok(url: str) -> bool:
    async with httpx.AsyncClient() as client, client.stream("GET", url) as resp:
        return resp.status_code == 200


class _FileType(NamedTuple):
    mime: str
    extension: str


def get_file_type(raw: bytes) -> _FileType:
    info = fleep.get(raw)
    return _FileType(info.mime[0], info.extension[0])


async def webm_to_gif(raw: bytes) -> bytes:
    cache_dir =  anyio.Path(get_plugin_cache_dir())
    webm_file = cache_dir / f"{id(raw)}.webm"
    gif_file = cache_dir / f"{id(raw)}.gif"

    await webm_file.write_bytes(raw)
    await anyio.run_process(["ffmpeg", "-i", str(webm_file), str(gif_file)])
    data = await gif_file.read_bytes()
    await webm_file.unlink()
    await gif_file.unlink()
    return data
