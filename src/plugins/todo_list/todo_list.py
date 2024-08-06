import json
from datetime import datetime
from typing import Annotated, Self

from nonebot.params import Depends
from nonebot_plugin_datastore import get_plugin_data
from nonebot_plugin_session import SessionId, SessionIdType
from pydantic import BaseModel


class Todo(BaseModel):
    content: str
    checked: bool
    pinned: bool
    time: datetime

    @classmethod
    def new(cls, content: str) -> Self:
        return cls(content=content, checked=False, pinned=False, time=datetime.now())


class TodoList:
    session_id: str
    todo: list[Todo]

    def __init__(self, session_id: str, todo: list[Todo]) -> None:
        self.session_id = session_id
        self.todo = todo

    @classmethod
    def load(cls, session_id: str) -> Self:
        fp = get_plugin_data().data_dir / f"{session_id}.json"
        if not fp.exists():
            fp.write_text("[]")
            return cls(session_id, [])
        data = json.loads(fp.read_text(encoding="utf-8"))
        return cls(
            session_id,
            [Todo.model_validate(i) for i in data],
        )

    def save(self) -> None:
        self.sort()
        (get_plugin_data().data_dir / f"{self.session_id}.json").write_text(
            json.dumps(
                [i.model_dump(mode="json") for i in self.todo],
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )

    def sort(self) -> None:
        self.todo.sort(key=lambda x: (1 - x.pinned, x.checked, x.time.timestamp()))

    def _get(self, index: int) -> Todo:
        return self.todo[index - 1]

    def add(self, content: str) -> Todo:
        todo = Todo.new(content)
        self.todo.append(todo)
        self.save()
        return todo

    def remove(self, index: int) -> None:
        self.todo.pop(index - 1)
        self.save()

    def check(self, index: int) -> None:
        self._get(index).checked = True
        self.save()

    def uncheck(self, index: int) -> None:
        self._get(index).checked = False
        self.save()

    def pin(self, index: int) -> None:
        self._get(index).pinned = True
        self.save()

    def unpin(self, index: int) -> None:
        self._get(index).pinned = False
        self.save()

    def show(self) -> str:
        result = [
            f"{'●' if i.checked else '○'} {'★ ' if i.pinned else ''}{i.content}"
            for i in self.todo
        ]
        return "\n".join(result)


def _user_todo(session_id: Annotated[str, SessionId(SessionIdType.USER)]) -> TodoList:
    return TodoList.load(session_id)


UserTodo = Annotated[TodoList, Depends(_user_todo)]
