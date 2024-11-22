import json
from collections.abc import Generator, Iterable
from datetime import datetime
from typing import Annotated, Any, Self

import aiofiles
from async_lru import alru_cache
from nonebot.params import Depends
from nonebot_plugin_alconna.uniseg import UniMessage
from nonebot_plugin_htmlrender import md_to_pic
from nonebot_plugin_localstore import get_plugin_data_dir
from nonebot_plugin_session import SessionId, SessionIdType
from pydantic import BaseModel


@alru_cache(1 << 4, ttl=120)
async def render_markdown(md: str) -> bytes:
    return await md_to_pic(md)


class Todo(BaseModel):
    content: str
    checked: bool
    pinned: bool
    time: datetime

    @classmethod
    def new(cls, content: str) -> Self:
        return cls(content=content, checked=False, pinned=False, time=datetime.now())

    def show_markdown(self, idx: int) -> str:
        check = "x" if self.checked else " "
        pin = "📌" if self.pinned else "&nbsp; &nbsp; &nbsp;"
        return f"- [{check}] {pin} **{idx}.** {self.content}"


class TodoList:
    session_id: str
    todo: list[Todo]

    def __init__(self, session_id: str, todo: list[Todo]) -> None:
        self.session_id = session_id
        self.todo = todo

    @classmethod
    async def load(
        cls, session_id: Annotated[str, SessionId(SessionIdType.USER)]
    ) -> Self:
        fp = get_plugin_data_dir() / f"{session_id}.json"
        if not fp.exists():
            fp.write_text("[]")
            return cls(session_id, [])

        async with aiofiles.open(fp, "r+", encoding="utf-8") as file:
            data = json.loads(await file.read())

        return cls(
            session_id,
            [Todo.model_validate(i) for i in data],
        )

    async def save(self) -> None:
        self.sort()
        fp = get_plugin_data_dir() / f"{self.session_id}.json"
        data = json.dumps(
            [i.model_dump(mode="json") for i in self.todo],
            ensure_ascii=False,
        )

        async with aiofiles.open(fp, "w+", encoding="utf-8") as file:
            await file.write(data)

    def sort(self) -> None:
        self.todo.sort(key=lambda x: (x.checked, 1 - x.pinned, x.time.timestamp()))

    async def get(self, index: int) -> Todo:
        i = index
        if index > 0:
            i = index - 1

        try:
            return self.todo[i]
        except IndexError:
            await UniMessage(f"没有序号为 {index} 的待办事项").finish()

    async def add(self, content: str) -> Todo:
        todo = Todo.new(content)
        self.todo.append(todo)
        await self.save()
        return todo

    async def remove(self, index: int) -> None:
        self.todo.remove(await self.get(index))
        await self.save()

    async def check(self, index: int) -> None:
        (await self.get(index)).checked = True
        await self.save()

    async def uncheck(self, index: int) -> None:
        (await self.get(index)).checked = False
        await self.save()

    async def pin(self, index: int) -> None:
        (await self.get(index)).pinned = True
        await self.save()

    async def unpin(self, index: int) -> None:
        (await self.get(index)).pinned = False
        await self.save()

    async def render(self, todo: Iterable[Todo] | None = None) -> bytes:
        md = "### 📝 Todo List\n"
        for i, t in enumerate(todo or self.todo, 1):
            md += f"{t.show_markdown(i)}\n"
        return await render_markdown(md)

    def checked(self) -> Generator[Todo, Any]:
        yield from (todo for todo in self.todo if todo.checked)

    async def purge(self) -> None:
        for todo in [*self.checked()]:
            self.todo.remove(todo)
        await self.save()


UserTodo = Annotated[TodoList, Depends(TodoList.load)]
