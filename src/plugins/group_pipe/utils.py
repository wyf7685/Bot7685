import contextlib
import copy
import pathlib
import shutil
from collections.abc import AsyncGenerator, AsyncIterable
from typing import NamedTuple

import anyio
import httpx
import nonebot
from nonebot_plugin_alconna.uniseg import Segment, UniMessage
from nonebot_plugin_alconna.uniseg.segment import Media
from nonebot_plugin_alconna.uniseg.utils import fleep
from nonebot_plugin_localstore import get_plugin_cache_dir


class _GlobalAsyncClient:
    client: httpx.AsyncClient

    @nonebot.get_driver().on_startup
    async def _() -> None:
        _GlobalAsyncClient.client = httpx.AsyncClient()
        await _GlobalAsyncClient.client.__aenter__()

    @nonebot.get_driver().on_shutdown
    async def _() -> None:
        await _GlobalAsyncClient.client.__aexit__(None, None, None)


def async_client() -> httpx.AsyncClient:
    return _GlobalAsyncClient.client


async def download_url(url: str) -> bytes:
    try:
        resp = await async_client().get(url)
        resp.raise_for_status()
    except (httpx.ConnectError, httpx.HTTPError):
        return b""
    else:
        return resp.read()


async def check_url_ok(url: str) -> bool:
    try:
        async with async_client().stream("GET", url) as resp:
            resp.raise_for_status()
    except (httpx.ConnectError, httpx.HTTPError):
        return False
    else:
        return True


class _FileType(NamedTuple):
    mime: str
    extension: str
    size: int


async def guess_url_type(url: str) -> _FileType | None:
    async with async_client().stream("GET", url) as resp:
        size = resp.headers.get("Content-Length")
        if not size:
            return None

        head = await anext(resp.aiter_bytes(256))
        info = fleep.get(head)
        if not info.mimes or not info.extensions:
            return None

        return _FileType(info.mimes[0], info.extensions[0], int(size))


async def solve_url_302(url: str) -> str:
    async with async_client().stream("GET", url) as resp:
        if resp.status_code == 302:
            return await solve_url_302(resp.headers["Location"].partition("?")[0])
    return url


type _AnyFile = bytes | anyio.Path | pathlib.Path


@contextlib.asynccontextmanager
async def _fix_file(file: _AnyFile) -> AsyncGenerator[anyio.Path]:
    if isinstance(file, bytes):
        info = fleep.get(file[:128])
        if not info.extensions:
            raise ValueError("无法识别的文件类型")

        path = anyio.Path(get_plugin_cache_dir()) / f"{id(file)}.{info.extensions[0]}"
        await path.write_bytes(file)
        try:
            yield path
        finally:
            await path.unlink()
        return

    if isinstance(file, pathlib.Path):
        file = anyio.Path(file)

    if not await file.exists():
        raise FileNotFoundError(f"文件 {file} 不存在")

    yield file


@contextlib.asynccontextmanager
async def _ffmpeg_transform(
    src_file: _AnyFile, dst_file_ext: str
) -> AsyncGenerator[anyio.Path]:
    dst_file = anyio.Path(get_plugin_cache_dir()) / f"{id(src_file)}.{dst_file_ext}"

    async with _fix_file(src_file) as src_file:
        result = await anyio.run_process(["ffmpeg", "-i", str(src_file), str(dst_file)])
        result.check_returncode()

    try:
        yield dst_file
    finally:
        await dst_file.unlink()


async def webm_to_gif(raw: bytes) -> bytes:
    async with _ffmpeg_transform(raw, "gif") as gif_file:
        return await gif_file.read_bytes()


async def amr_to_mp3(file: pathlib.Path) -> AsyncIterable[pathlib.Path]:
    tmpfile = shutil.copyfile(file, get_plugin_cache_dir() / file.name)

    cmd = [
        "/silk-v3-decoder/converter.sh",
        str(tmpfile),
        "mp3",
    ]
    result = await anyio.run_process(cmd)
    result.check_returncode()

    output = tmpfile.with_name(f"{file.stem}.mp3")
    yield output
    tmpfile.unlink()
    output.unlink()


def _repr_uniseg(seg: Segment) -> str:
    if isinstance(seg, Media) and seg.raw is not None:
        (seg := copy.copy(seg)).raw = b"..."
    return repr(seg)


def repr_unimsg[TS: Segment](msg: UniMessage[TS]) -> str:
    return "[" + ", ".join(_repr_uniseg(seg) for seg in msg) + "]"
