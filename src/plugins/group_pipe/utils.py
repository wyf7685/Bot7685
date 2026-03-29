import contextlib
import copy
import functools
import io
import pathlib
from collections.abc import AsyncGenerator, AsyncIterator, Callable
from contextvars import ContextVar
from types import CoroutineType, TracebackType
from typing import Any, NamedTuple, Self

import anyio
import httpx
import yarl
from nonebot.utils import run_sync
from nonebot_plugin_alconna.uniseg import Segment, UniMessage
from nonebot_plugin_alconna.uniseg.segment import Media
from nonebot_plugin_alconna.uniseg.utils import fleep
from nonebot_plugin_localstore import get_plugin_cache_dir


class _ContextClientHolder:
    def __init__(self) -> None:
        self.client: httpx.AsyncClient | None = None

    async def get(self) -> httpx.AsyncClient:
        if self.client is None:
            self.client = httpx.AsyncClient()
            await self.client.__aenter__()
        return self.client

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None = None,
        exc_value: BaseException | None = None,
        traceback: TracebackType | None = None,
    ) -> None:
        if self.client is not None:
            await self.client.__aexit__(exc_type, exc_value, traceback)
            self.client = None


_ctx_client = ContextVar[_ContextClientHolder | None](
    "group_pipe:context_client", default=None
)


@contextlib.asynccontextmanager
async def async_client() -> AsyncIterator[httpx.AsyncClient]:
    if holder := _ctx_client.get():
        yield await holder.get()
        return

    async with httpx.AsyncClient() as client:
        yield client


@contextlib.asynccontextmanager
async def enter_client_ctx() -> AsyncIterator[None]:
    if _ctx_client.get() is not None:
        yield
        return

    async with _ContextClientHolder() as holder:
        with _ctx_client.set(holder):
            yield


def with_client_ctx[**P, R](
    func: Callable[P, CoroutineType[Any, Any, R]],
) -> Callable[P, CoroutineType[Any, Any, R]]:
    @functools.wraps(func)
    async def wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
        async with enter_client_ctx():
            return await func(*args, **kwargs)

    return wrapper


def fix_url(url: str) -> str:
    parsed = yarl.URL(url)
    if parsed.host == "multimedia.nt.qq.com.cn":
        parsed = parsed.with_scheme("http")
    return str(parsed)


async def download_url(url: str) -> bytes:
    url = fix_url(url)
    try:
        async with async_client() as client:
            resp = await client.get(url)
        resp.raise_for_status()
    except httpx.ConnectError, httpx.HTTPError:
        return b""
    else:
        return resp.read()


async def check_url_ok(url: str) -> bool:
    url = fix_url(url)
    try:
        async with (
            async_client() as client,
            client.stream("GET", url) as resp,
        ):
            resp.raise_for_status()
    except httpx.ConnectError, httpx.HTTPError:
        return False
    else:
        return True


class _FileType(NamedTuple):
    mime: str
    extension: str
    size: int


async def guess_url_type(url: str) -> _FileType | None:
    url = fix_url(url)
    async with (
        async_client() as client,
        client.stream("GET", url) as resp,
    ):
        size = resp.headers.get("Content-Length")
        if not size:
            return None

        head = await anext(resp.aiter_bytes(256))
        info = fleep.get(head)
        if not info.mimes or not info.extensions:
            return None

        return _FileType(info.mimes[0], info.extensions[0], int(size))


async def solve_url_302(url: str) -> str:
    url = fix_url(url)
    async with (
        async_client() as client,
        client.stream("GET", url) as resp,
    ):
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


@run_sync
def webm_to_gif(raw: bytes) -> bytes:
    import imageio

    reader = imageio.get_reader(io.BytesIO(raw), format="webm")  # pyright: ignore[reportArgumentType]
    fps = reader.get_meta_data().get("fps", 10)
    duration = reader.get_meta_data().get("duration", 0)
    writer_kwds = {"format": "gif", "fps": fps, "duration": duration, "loop": 0}
    with io.BytesIO() as output:
        writer = imageio.get_writer(output, **writer_kwds)
        for frame in reader.iter_data():
            writer.append_data(frame)
        writer.close()
        return output.getvalue()


def _repr_uniseg(seg: Segment) -> str:
    if isinstance(seg, Media) and seg.raw is not None:
        (seg := copy.copy(seg)).raw = b"..."
    return repr(seg)


def repr_unimsg[TS: Segment](msg: UniMessage[TS]) -> str:
    return "[" + ", ".join(_repr_uniseg(seg) for seg in msg) + "]"
