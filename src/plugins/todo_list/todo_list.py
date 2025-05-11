import json
from collections.abc import Generator, Iterable
from datetime import datetime
from typing import Annotated

import anyio
from nonebot.adapters import Bot, Event
from nonebot.compat import type_validate_json
from nonebot.params import Depends
from nonebot_plugin_alconna.uniseg import UniMessage
from nonebot_plugin_htmlrender import md_to_pic
from nonebot_plugin_localstore import get_plugin_data_dir
from nonebot_plugin_session import SessionIdType, extract_session
from pydantic import BaseModel, Field

from src.plugins.cache import cache_with

render_markdown = cache_with(str, namespace="todo_list:md_render", key=hash)(md_to_pic)


class Todo(BaseModel):
    content: str
    checked: bool = False
    pinned: bool = False
    time: datetime = Field(default_factory=datetime.now)

    def show(self, idx: int) -> str:
        check = "x" if self.checked else " "
        pin = "📌" if self.pinned else "&nbsp; &nbsp; &nbsp;"
        return f"- [{check}] {pin} **{idx}.** {self.content}"


class TodoList:
    session_id: str
    todo: list[Todo]
    current: Todo | None

    def __init__(self, session_id: str, todo: list[Todo]) -> None:
        self.session_id = session_id
        self.todo = todo
        self.current = None

    async def save(self) -> None:
        self.sort()
        fp = anyio.Path(get_plugin_data_dir()) / f"{self.session_id}.json"
        data = json.dumps(
            [i.model_dump(mode="json") for i in self.todo],
            ensure_ascii=False,
        )

        await fp.write_text(data, encoding="utf-8")

    def sort(self) -> None:
        self.todo.sort(key=lambda x: (x.checked, 1 - x.pinned, x.time.timestamp()))

    async def check_index(self, index: int) -> None:
        if not (1 <= index <= len(self.todo)):
            await UniMessage(f"没有序号为 {index} 的待办事项").finish()

    def get(self, index: int) -> Todo:
        self.current = self.todo[index - 1]
        return self.current

    def add(self, content: str) -> Todo:
        self.current = Todo(content=content)
        self.todo.append(self.current)
        return self.current

    def remove(self, index: int) -> None:
        self.todo.remove(self.get(index))
        self.current = None

    def check(self, index: int) -> None:
        self.get(index).checked = True

    def uncheck(self, index: int) -> None:
        self.get(index).checked = False

    def pin(self, index: int) -> None:
        self.get(index).pinned = True

    def unpin(self, index: int) -> None:
        self.get(index).pinned = False

    async def render(self, todo: Iterable[Todo] | None = None) -> bytes:
        md = "### 📝 Todo List\n"
        for i, t in enumerate(todo or self.todo, 1):
            md += f"{t.show(i)}\n"
        return await render_markdown(md)

    def checked(self) -> Generator[Todo]:
        yield from (todo for todo in self.todo if todo.checked)

    def clear(self) -> None:
        for todo in [*self.checked()]:
            self.todo.remove(todo)
        self.current = None


async def _user_todo(bot: Bot, event: Event) -> TodoList:
    session_id = extract_session(bot, event).get_id(SessionIdType.USER)
    fp = anyio.Path(get_plugin_data_dir()) / f"{session_id}.json"
    if not await fp.exists():
        await fp.write_text("[]")
        return TodoList(session_id, [])

    data = type_validate_json(list[Todo], await fp.read_text(encoding="utf-8"))
    return TodoList(session_id, data)


UserTodo = Annotated[TodoList, Depends(_user_todo)]
