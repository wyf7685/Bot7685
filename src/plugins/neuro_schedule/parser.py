import contextlib
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Literal

import httpx
from nonebot import logger
from nonebot.adapters.discord.api.types import TimeStampStyle
from nonebot.adapters.discord.message import (
    AttachmentSegment,
    CustomEmojiSegment,
    Message,
    TextSegment,
    TimestampSegment,
)
from nonebot_plugin_localstore import get_plugin_cache_dir

from .models import Emoji, ScheduleData, ScheduleEntry, Text

type SegType = Literal["text", "ldt", "ld", "rt", "emoji", "attachment", "newline"]
_TSS_TYPE_MAP: dict[TimeStampStyle, SegType] = {
    TimeStampStyle.LongDateTime: "ldt",
    TimeStampStyle.LongDate: "ld",
    TimeStampStyle.RelativeTime: "rt",
}


def _extract_segs(msg: Message) -> list[tuple[SegType, Any]]:
    segs: list[tuple[SegType, Any]] = []
    for seg in msg:
        match seg:
            case TextSegment(data={"text": str(text)}) if text := text.strip():
                for idx, line in enumerate(text.splitlines()):
                    if idx > 0:
                        segs.append(("newline", None))
                    segs.append(("text", line))
            case TimestampSegment(
                data={
                    "timestamp": int() | float() as ts,
                    "style": TimeStampStyle() as style,
                },
            ):
                segs.append((_TSS_TYPE_MAP[style], datetime.fromtimestamp(ts, tz=UTC)))
            case CustomEmojiSegment(data=data):
                segs.append(("emoji", Emoji.model_validate(data)))
            case AttachmentSegment(data={"url": str(url)}) if url:
                segs.append(("attachment", url))
    return segs


async def _download_image(url: str) -> Path:
    path = get_plugin_cache_dir() / f"{uuid.uuid4().hex}.png"
    async with httpx.AsyncClient() as client:
        resp = await client.get(url, follow_redirects=True)
        resp.raise_for_status()
        path.write_bytes(resp.content)
    return path


class ScheduleParser:
    def __init__(self, msg: Message) -> None:
        self.segs = _extract_segs(msg)
        self.idx = 0

    @property
    def _has_more(self) -> bool:
        return self.idx < len(self.segs)

    @property
    def _current(self) -> tuple[SegType, Any]:
        return self.segs[self.idx]

    @property
    def _current_type(self) -> SegType | None:
        return self._current[0] if self._has_more else None

    @property
    def _current_data(self) -> Any:
        return self._current[1] if self._has_more else None

    def _consume(self) -> None:
        self.idx += 1

    def _pop(self) -> tuple[SegType, Any]:
        seg = self._current
        self._consume()
        return seg

    def _collect_event(self) -> tuple[Text | Emoji, ...]:
        content: list[Text | Emoji] = []
        while self._current_type in ("text", "emoji"):
            if self._current_type == "text":
                text: str = self._current_data
                if not any(isinstance(item, Text) for item in content):
                    text = text.strip(" -")
                if text.lstrip(" \n-#").startswith("Fanart of the week"):
                    break
                if text:
                    content.append(Text(text=text))
            else:
                content.append(self._current_data)
            self._consume()
        return tuple(content)

    def parse_entries(self) -> list[ScheduleEntry]:
        entries: list[ScheduleEntry] = []
        while self._has_more:
            seg_type, seg_data = self._pop()
            if seg_type in {"ldt", "ld"}:
                ts: datetime = seg_data
                if (
                    self._current_type == "text"
                    and str(self._current_data).strip() == "-"
                ):
                    self._consume()
                if self._current_type == "rt":
                    self._consume()
                content = self._collect_event()
                entries.append(ScheduleEntry(timestamp=ts, content=content))
        return entries

    async def _parse_image(self) -> Path | None:
        gen = (
            seg_data
            for seg_type, seg_data in reversed(self.segs)
            if seg_type == "attachment"
        )
        if not (url := next(gen, None)):
            return None

        try:
            return await _download_image(url)
        except Exception:
            logger.exception("下载图片失败")
            return None

    async def parse(self) -> ScheduleData:
        entries = self.parse_entries()
        schedule_image = await self._parse_image()
        return ScheduleData(entries=entries, schedule_image=schedule_image)


async def parse_schedule(msg: Message) -> ScheduleData:
    return await ScheduleParser(msg).parse()


def _is_similar(a: str, b: str) -> bool:
    from rapidfuzz.fuzz import token_set_ratio

    return token_set_ratio(a, b) >= 85


def merge_schedule_data(old: ScheduleData, new: ScheduleData) -> ScheduleData:
    old_entries = [
        e
        for e in old.entries
        if not any(_is_similar(e.plain_text, ne.plain_text) for ne in new.entries)
    ]
    entries = sorted(old_entries + new.entries, key=lambda e: e.timestamp)
    if latest_ts := max(e.timestamp for e in entries) if entries else None:
        start_of_week = latest_ts.replace(
            hour=0, minute=0, second=0, microsecond=0
        ) - timedelta(days=7)
        entries = [e for e in entries if e.timestamp >= start_of_week]
    if new.schedule_image is not None:
        if old.schedule_image is not None:
            with contextlib.suppress(Exception):
                old.schedule_image.unlink(missing_ok=True)
        schedule_image = new.schedule_image
    else:
        schedule_image = old.schedule_image
    return ScheduleData(entries=entries, schedule_image=schedule_image)
