from datetime import UTC, datetime
from typing import Annotated

from nonebot.params import Depends
from nonebot_plugin_alconna.uniseg import UniMessage
from nonebot_plugin_htmlrender import render_markdown
from nonebot_plugin_orm import AsyncSession, Model, get_session
from nonebot_plugin_user import User
from pydantic import BaseModel, Field
from sqlalchemy import Boolean, DateTime, Integer, Text, delete, select
from sqlalchemy.orm import Mapped, mapped_column

from src.utils import attach_async_context


class TodoItem(Model):
    __tablename__ = "todo_item"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    checked: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    pinned: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )


class Todo(BaseModel):
    id: int | None = None
    content: str
    checked: bool = False
    pinned: bool = False
    time: datetime = Field(default_factory=lambda: datetime.now(UTC))

    def show(self, idx: int) -> str:
        check = "x" if self.checked else " "
        pin = "📌" if self.pinned else "&nbsp; &nbsp; &nbsp;"
        return f"- [{check}] {pin} **{idx}.** {self.content}"


@attach_async_context(get_session)
async def _load_todos(session: AsyncSession, user_id: int) -> list[Todo]:
    statement = (
        select(TodoItem)
        .where(TodoItem.user_id == user_id)
        .order_by(
            TodoItem.checked,
            TodoItem.pinned.desc(),
            TodoItem.created_at,
            TodoItem.id,
        )
    )
    rows = (await session.scalars(statement)).all()
    return [
        Todo(
            id=row.id,
            content=row.content,
            checked=row.checked,
            pinned=row.pinned,
            time=row.created_at,
        )
        for row in rows
    ]


@attach_async_context(get_session)
async def _save_todos(
    session: AsyncSession,
    user_id: int,
    todos: list[Todo],
    deleted_ids: set[int],
) -> None:
    if deleted_ids:
        await session.execute(
            delete(TodoItem).where(
                TodoItem.user_id == user_id,
                TodoItem.id.in_(deleted_ids),
            )
        )

    persisted_ids = [todo.id for todo in todos if todo.id is not None]
    rows = (
        (
            await session.scalars(
                select(TodoItem).where(
                    TodoItem.user_id == user_id,
                    TodoItem.id.in_(persisted_ids),
                )
            )
        ).all()
        if persisted_ids
        else []
    )
    existing = {row.id: row for row in rows}
    inserted: list[tuple[Todo, TodoItem]] = []

    for todo in todos:
        row = existing.get(todo.id) if todo.id is not None else None
        if row is None:
            row = TodoItem(
                user_id=user_id,
                content=todo.content,
                checked=todo.checked,
                pinned=todo.pinned,
                created_at=todo.time,
            )
            session.add(row)
            inserted.append((todo, row))
            continue
        row.content = todo.content
        row.checked = todo.checked
        row.pinned = todo.pinned
        row.created_at = todo.time

    await session.flush()
    for todo, row in inserted:
        todo.id = row.id
    await session.commit()


class TodoList:
    user_id: int
    todo: list[Todo]
    current: Todo | None

    def __init__(self, user_id: int, todo: list[Todo]) -> None:
        self.user_id = user_id
        self.todo = todo
        self.current = None
        self._deleted_ids: set[int] = set()

    async def save(self) -> None:
        self.sort()
        await _save_todos(self.user_id, self.todo, self._deleted_ids)
        self._deleted_ids.clear()

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
        todo = self.get(index)
        self.todo.remove(todo)
        if todo.id is not None:
            self._deleted_ids.add(todo.id)
        self.current = None

    async def render(self, todo: list[Todo] | None = None) -> bytes:
        md = "### 📝 Todo List\n"
        for i, item in enumerate(todo or self.todo, 1):
            md += f"{item.show(i)}\n"
        rendered = await render_markdown(md)
        return rendered.data

    def checked(self) -> list[Todo]:
        return [todo for todo in self.todo if todo.checked]

    def clear_checked(self) -> None:
        for todo in self.checked():
            self.todo.remove(todo)
            if todo.id is not None:
                self._deleted_ids.add(todo.id)
        self.current = None


async def _user_todo(user: User) -> TodoList:
    return TodoList(user.id, await _load_todos(user.id))


UserTodo = Annotated[TodoList, Depends(_user_todo)]


async def _selected_todo(user_todo: UserTodo, index: int) -> Todo:
    await user_todo.check_index(index)
    return user_todo.get(index)


SelectedTodo = Annotated[Todo, Depends(_selected_todo)]
