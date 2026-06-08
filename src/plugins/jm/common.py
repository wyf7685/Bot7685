import contextlib
from abc import ABC, abstractmethod
from collections import deque
from collections.abc import AsyncGenerator
from typing import ClassVar

import anyio
import httpx
from nonebot import logger
from nonebot.exception import NetworkError
from nonebot_plugin_alconna import CustomNode, UniMessage
from nonebot_plugin_alconna.uniseg import Receipt

from src.utils import schedule_recall

from .utils import Future, abatched, aenumerate

SEG_BATCH_SIZE = 20


async def send_nodes(nodes: list[CustomNode]) -> None:
    try:
        await UniMessage.reference(*nodes).send()
    except NetworkError as exc:
        logger.warning(f"发送合并转发时发生网络错误: {exc!r}")


class Downloader[Index, Task](ABC):
    concurrency: ClassVar[int] = 10

    httpx_client: httpx.AsyncClient | None = None
    stack: contextlib.AsyncExitStack | None = None

    @abstractmethod
    def create_httpx_client(self) -> httpx.AsyncClient:
        raise NotImplementedError

    async def get_httpx_client(self) -> httpx.AsyncClient:
        if self.httpx_client is None:
            self.httpx_client = self.create_httpx_client()
            if self.stack is not None:
                await self.stack.enter_async_context(self.httpx_client)

        return self.httpx_client

    @abstractmethod
    async def fetch_index(self, id: int, /) -> Index:
        raise NotImplementedError

    @abstractmethod
    async def format_summary(self, index: Index, /) -> str:
        raise NotImplementedError

    @abstractmethod
    async def generate_task(self, index: Index, /) -> AsyncGenerator[tuple[str, Task]]:
        raise NotImplementedError
        yield

    @abstractmethod
    async def execute_task(self, task: Task, /) -> bytes:
        raise NotImplementedError

    async def iter_items(
        self, index: Index, /
    ) -> AsyncGenerator[tuple[str, str | bytes]]:
        async def run_task(task: Task, future: Future[str | bytes]) -> None:
            try:
                result = await self.execute_task(task)
            except Exception as exc:
                future.set_result(repr(exc))
            else:
                future.set_result(result)

        running: deque[tuple[str, Future[str | bytes]]] = deque()
        async with (
            contextlib.AsyncExitStack() as self.stack,
            anyio.create_task_group() as tg,
            contextlib.aclosing(self.generate_task(index)) as task_gen,
        ):
            async for name, task in task_gen:
                if len(running) == self.concurrency:
                    current = running.popleft()
                    yield current[0], await current[1]
                future = Future[str | bytes]()
                tg.start_soon(run_task, task, future)
                running.append((name, future))
            while running:
                current = running.popleft()
                yield current[0], await current[1]

    async def send_forward(self, id: int, node_uid: str, receipt: Receipt) -> None:
        try:
            index = await self.fetch_index(id)
        except Exception as err:
            await UniMessage.text(f"获取信息失败: 未知错误\n{err!r}").finish()

        formatted = await self.format_summary(index)
        await UniMessage.text(formatted).send(reply_to=True)
        schedule_recall(receipt)

        async with (
            contextlib.aclosing(self.iter_items(index)) as agen,
            anyio.create_task_group() as tg,
        ):
            async for idx, batch in aenumerate(abatched(agen, SEG_BATCH_SIZE), start=1):
                nodes = [
                    CustomNode(
                        uid=node_uid,
                        name=name,
                        content=UniMessage.image(raw=raw)
                        if isinstance(raw, bytes)
                        else UniMessage.text(f"[图片下载失败: {raw}]"),
                    )
                    for name, raw in batch
                ]
                logger.opt(colors=True).info(f"开始发送合并转发: <c>{idx}</c>")
                tg.start_soon(send_nodes, nodes)
