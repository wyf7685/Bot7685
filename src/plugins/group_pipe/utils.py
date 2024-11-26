import copy
from typing import NamedTuple

import anyio
import fleep
import httpx
import nonebot
from nonebot_plugin_alconna.uniseg import Segment, UniMessage
from nonebot_plugin_alconna.uniseg.segment import Media
from nonebot_plugin_localstore import get_plugin_cache_dir


class _SharedClient:
    client: httpx.AsyncClient

    @nonebot.get_driver().on_startup
    async def _() -> None:
        _SharedClient.client = httpx.AsyncClient()
        await _SharedClient.client.__aenter__()

    @nonebot.get_driver().on_shutdown
    async def _() -> None:
        await _SharedClient.client.__aexit__(None, None, None)


def get_httpx_client() -> httpx.AsyncClient:
    return _SharedClient.client


async def download_url(url: str) -> bytes:
    try:
        resp = await get_httpx_client().get(url)
        resp.raise_for_status()
    except (httpx.ConnectError, httpx.HTTPError):
        return b""
    else:
        return resp.read()


async def check_url_ok(url: str) -> bool:
    async with get_httpx_client().stream("GET", url) as resp:
        return resp.status_code == 200


class _FileType(NamedTuple):
    mime: str
    extension: str
    size: int


async def guess_url_type(url: str) -> _FileType | None:
    async with get_httpx_client().stream("GET", url) as resp:
        size = resp.headers.get("Content-Length")
        if not size:
            return None

        head = await anext(resp.aiter_bytes(128))
        info = fleep.get(head)
        return _FileType(info.mime[0], info.extension[0], int(size))


async def webm_to_gif(raw: bytes) -> bytes:
    cache_dir = anyio.Path(get_plugin_cache_dir())
    webm_file = cache_dir / f"{id(raw)}.webm"
    gif_file = cache_dir / f"{id(raw)}.gif"

    await webm_file.write_bytes(raw)
    result = await anyio.run_process(["ffmpeg", "-i", str(webm_file), str(gif_file)])
    result.check_returncode()
    data = await gif_file.read_bytes()
    await webm_file.unlink()
    await gif_file.unlink()
    return data


def _repr_uniseg(seg: Segment) -> str:
    if isinstance(seg, Media):
        seg = copy.copy(seg)
        seg.raw = b"..."
    return repr(seg)


def repr_unimsg[TS: Segment](msg: UniMessage[TS]) -> str:
    return "[" + ", ".join(_repr_uniseg(seg) for seg in msg) + "]"
