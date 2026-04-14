import contextlib
import copy
import io
from collections.abc import AsyncIterator, Callable
from contextvars import ContextVar
from types import CoroutineType, TracebackType
from typing import Any, NamedTuple, Self

import httpx
import yarl
from nonebot.utils import run_sync
from nonebot_plugin_alconna.uniseg import Segment, UniMessage
from nonebot_plugin_alconna.uniseg.segment import Media
from nonebot_plugin_alconna.uniseg.utils import fleep

from src.utils import attach_async_context


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
    return attach_async_context(enter_client_ctx, as_param=False)(func)


def fix_url(url: str) -> str:
    parsed = yarl.URL(url)
    if parsed.host == "multimedia.nt.qq.com.cn":
        parsed = parsed.with_scheme("http")
    return str(parsed)


@attach_async_context(async_client)
async def download_url(client: httpx.AsyncClient, url: str) -> bytes:
    url = fix_url(url)
    try:
        resp = await client.get(url)
        resp.raise_for_status()
    except httpx.ConnectError, httpx.HTTPError:
        return b""
    else:
        return resp.read()


@attach_async_context(async_client)
async def check_url_ok(client: httpx.AsyncClient, url: str) -> bool:
    url = fix_url(url)
    try:
        async with client.stream("GET", url) as resp:
            resp.raise_for_status()
    except httpx.ConnectError, httpx.HTTPError:
        return False
    else:
        return True


class _FileType(NamedTuple):
    mime: str
    extension: str
    size: int


@attach_async_context(async_client)
async def guess_url_type(client: httpx.AsyncClient, url: str) -> _FileType | None:
    url = fix_url(url)
    async with client.stream("GET", url) as resp:
        size = resp.headers.get("Content-Length")
        if not size:
            return None

        head = await anext(resp.aiter_bytes(256))
        info = fleep.get(head)
        if not info.mimes or not info.extensions:
            return None

        return _FileType(info.mimes[0], info.extensions[0], int(size))


@attach_async_context(async_client)
async def solve_url_302(client: httpx.AsyncClient, url: str) -> str:
    url = fix_url(url)
    async with client.stream("GET", url) as resp:
        if resp.status_code == 302:
            return await solve_url_302(resp.headers["Location"].partition("?")[0])
    return url


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
