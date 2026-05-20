import uuid
from datetime import UTC, datetime
from pathlib import Path

import httpx
from nonebot import logger
from nonebot.adapters.discord.api.types import TimeStampStyle
from nonebot.adapters.discord.message import (
    AttachmentSegment,
    CustomEmojiSegment,
    Message,
    MessageSegment,
    TextSegment,
    TimestampSegment,
)
from nonebot_plugin_localstore import get_plugin_cache_dir

from .models import Emoji, ScheduleData, ScheduleEntry, Text


def _is_ts(seg: MessageSegment, style: TimeStampStyle | None = None) -> bool:
    if not isinstance(seg, TimestampSegment):
        return False
    return seg.data.get("style") == style if style is not None else True


def _is_text(segs: list[MessageSegment], idx: int, expected: str | None = None) -> bool:
    if idx >= len(segs) or not isinstance(segs[idx], TextSegment):
        return False
    return segs[idx].data["text"] == expected if expected is not None else True


def _collect_event(
    segs: list[MessageSegment], idx: int
) -> tuple[list[Text | Emoji], int]:
    content: list[Text | Emoji] = []
    while idx < len(segs):
        if _is_text(segs, idx):
            text = str(segs[idx].data["text"])
            if not any(isinstance(item, Text) for item in content):
                text = text.strip(" -")
            if text.lstrip(" \n-#").startswith("Fanart of the week"):
                break
            if text:
                content.append(Text(text=text))
        elif isinstance(segs[idx], CustomEmojiSegment):
            content.append(Emoji.model_validate(segs[idx].data))
        else:
            break
        idx += 1
    return content, idx


async def _download_image(url: str) -> Path:
    path = get_plugin_cache_dir() / f"{uuid.uuid4().hex}.png"
    async with httpx.AsyncClient() as client:
        resp = await client.get(url, follow_redirects=True)
        resp.raise_for_status()
        path.write_bytes(resp.content)
    return path


async def _parse_image(segs: list[MessageSegment]) -> Path | None:
    for seg in reversed(segs):
        if isinstance(seg, AttachmentSegment) and (url := seg.data.get("url", "")):
            try:
                return await _download_image(url)
            except Exception:
                logger.exception("下载图片失败")
    return None


async def parse_schedule(msg: Message) -> ScheduleData:
    segs = list(msg)
    entries: list[ScheduleEntry] = []
    idx = 0

    while idx < len(segs):
        seg = segs[idx]

        if _is_ts(seg, TimeStampStyle.LongDateTime):
            ts = datetime.fromtimestamp(seg.data["timestamp"], tz=UTC)
            idx += 1
            if _is_text(segs, idx, " - "):
                idx += 1
            if idx < len(segs) and _is_ts(segs[idx], TimeStampStyle.RelativeTime):
                idx += 1
            content, idx = _collect_event(segs, idx)
            entries.append(ScheduleEntry(timestamp=ts, content=content))

        elif _is_ts(seg, TimeStampStyle.LongDate):
            ts = datetime.fromtimestamp(seg.data["timestamp"], tz=UTC)
            idx += 1
            if _is_text(segs, idx, " - "):
                idx += 1
            content, idx = _collect_event(segs, idx)
            entries.append(ScheduleEntry(timestamp=ts, content=content))

        else:
            idx += 1

    schedule_image = await _parse_image(segs)
    return ScheduleData(entries=entries, schedule_image=schedule_image)
