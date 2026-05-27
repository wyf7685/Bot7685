import functools
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

from pydantic import BaseModel
from tzlocal import get_localzone


class Text(BaseModel):
    type: Literal["text"] = "text"
    text: str


class Emoji(BaseModel):
    type: Literal["emoji"] = "emoji"
    id: str
    name: str

    @property
    def url(self) -> str:
        return f"https://cdn.discordapp.com/emojis/{self.id}.webp"


class ScheduleEntry(BaseModel):
    timestamp: datetime
    content: tuple[Text | Emoji, ...]

    @functools.cached_property
    def plain_text(self) -> str:
        return "".join(item.text for item in self.content if item.type == "text")

    @functools.cached_property
    def is_offline(self) -> bool:
        return "offline" in self.plain_text.lower()

    @functools.cached_property
    def local_datetime(self) -> datetime:
        return self.timestamp.astimezone(get_localzone())

    @property
    def date_str(self) -> str:
        return self.local_datetime.strftime("%m月%d日")

    @property
    def time_str(self) -> str | None:
        if self.is_offline:
            return None
        return self.local_datetime.strftime("%H:%M")

    @property
    def relative_str(self) -> str:
        now = datetime.now(UTC)
        delta = self.timestamp - now
        total_seconds = int(delta.total_seconds())
        is_past = total_seconds < 0
        abs_seconds = abs(total_seconds)

        if abs_seconds < 3600:
            minutes = max(abs_seconds // 60, 1)
            text = f"{minutes} 分钟"
        elif abs_seconds < 86400:
            hours = abs_seconds // 3600
            text = f"{hours} 小时"
        else:
            days = abs_seconds // 86400
            text = f"{days} 天"

        if is_past:
            return f"{text}前"
        return f"{text}后" if abs_seconds < 86400 else f"{text}内"


class ScheduleData(BaseModel):
    entries: list[ScheduleEntry]
    schedule_image: Path | None = None
