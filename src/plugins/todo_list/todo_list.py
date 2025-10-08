import json
from datetime import datetime
from typing import TYPE_CHECKING, Annotated

import anyio
from nonebot.compat import type_validate_json
from nonebot.params import Depends
from nonebot_plugin_alconna.uniseg import UniMessage
from nonebot_plugin_htmlrender import md_to_pic
from nonebot_plugin_localstore import get_plugin_data_dir
from pydantic import BaseModel, Field

from src.plugins.cache import cache_with

if TYPE_CHECKING:
    from nonebot_plugin_user import User

render_markdown = cache_with(
    str,
    namespace="todo_list:md_render",
    key=hash,
    pickle=True,
)(md_to_pic)


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
    user_id: int
    todo: list[Todo]
    current: Todo | None

    def __init__(self, user_id: int, todo: list[Todo]) -> None:
        self.user_id = user_id
        self.todo = todo
        self.current = None

    async def save(self) -> None:
        self.sort()
        fp = anyio.Path(get_plugin_data_dir()) / f"{self.user_id}.json"
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

    async def render(self, todo: list[Todo] | None = None) -> bytes:
        md = "### 📝 Todo List\n"
        for i, t in enumerate(todo or self.todo, 1):
            md += f"{t.show(i)}\n"
        return await render_markdown(md)

    def checked(self) -> list[Todo]:
        return [todo for todo in self.todo if todo.checked]

    def clear_checked(self) -> None:
        for todo in self.checked():
            self.todo.remove(todo)
        self.current = None


async def _user_todo(user: User) -> TodoList:
    user_id = user.id
    fp = anyio.Path(get_plugin_data_dir()) / f"{user_id}.json"
    if not await fp.exists():
        await fp.write_text("[]")
        return TodoList(user_id, [])

    data = type_validate_json(list[Todo], await fp.read_text(encoding="utf-8"))
    return TodoList(user_id, data)


UserTodo = Annotated[TodoList, Depends(_user_todo)]


async def _selected_todo(user_todo: UserTodo, index: int) -> Todo:
    await user_todo.check_index(index)
    return user_todo.get(index)


SelectedTodo = Annotated[Todo, Depends(_selected_todo)]
