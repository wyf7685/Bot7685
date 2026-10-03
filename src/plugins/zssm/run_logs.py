from __future__ import annotations

import asyncio
import json
import re
from collections import deque
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field
from pathlib import Path
from time import perf_counter
from typing import Literal

from nonebot import get_driver, logger
from nonebot.utils import escape_tag
from nonebot_plugin_htmlrender import get_default_application, render_template_html

from src.service.cache import get_cache
from src.utils import format_exception

_RunStatus = Literal["completed", "failed", "cancelled"]
_LLM_COMPONENTS = frozenset({"LLM::Agent", "LLM::Tools"})
_MAX_RUN_LOG_LINES = 240
_MAX_RUN_LOG_TEXT_CHARS = 20_000
_MAX_RUN_LOG_LINE_CHARS = 1_200
_LOG_MARKUP_RE = re.compile(r"</>|</?(?:b|c|g|m|r|y)>")
_ANSI_ESCAPE_RE = re.compile(r"\x1b(?:\[[0-?]*[ -/]*[@-~]|\][^\x07]*(?:\x07|\x1b\\))")
_CONTROL_CHAR_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
_TEMPLATE_DIR = Path(__file__).with_name("templates")

current_run_id: ContextVar[str | None] = ContextVar("current_run_id", default=None)
_current_run_log: ContextVar[RunLogCapture | None] = ContextVar(
    "current_run_log", default=None
)


@dataclass(slots=True)
class RunLogCapture:
    run_id: str
    started: float
    _lines: deque[str] = field(default_factory=deque)
    _text_chars: int = 0
    _truncated_lines: int = 0
    status: _RunStatus | None = None
    closed: bool = False

    def close(self) -> None:
        self.closed = True

    def append(self, level: str, component: str, message: str) -> None:
        if self.closed:
            return
        clean_message = _clean_log_text(message)
        message_lines = clean_message.splitlines() or [""]
        elapsed_ms = (perf_counter() - self.started) * 1000
        normalized_level = level.upper()[:7]
        normalized_component = _clean_log_text(component)[:48]

        for index, message_line in enumerate(message_lines):
            if index == 0:
                prefix = (
                    f"{elapsed_ms:8.1f}ms {normalized_level:<7} "
                    f"{normalized_component} | "
                )
            else:
                prefix = f"{elapsed_ms:8.1f}ms {"":7} {"":48} | "
            available = max(0, _MAX_RUN_LOG_LINE_CHARS - len(prefix))
            if len(message_line) > available:
                suffix = "… [line truncated]"
                message_line = message_line[: max(0, available - len(suffix))] + suffix
            line = prefix + message_line
            line_chars = len(line) + 1

            while self._lines and (
                len(self._lines) >= _MAX_RUN_LOG_LINES
                or self._text_chars + line_chars > _MAX_RUN_LOG_TEXT_CHARS - 128
            ):
                removed = self._lines.popleft()
                self._text_chars -= len(removed) + 1
                self._truncated_lines += 1

            if line_chars > _MAX_RUN_LOG_TEXT_CHARS - 128:
                self._truncated_lines += 1
                continue
            self._lines.append(line)
            self._text_chars += line_chars

    def render_text(self) -> str:
        lines: list[str] = []
        if self._truncated_lines:
            lines.append(
                f"… {self._truncated_lines} earlier log lines truncated; "
                f"showing the most recent {len(self._lines)} …"
            )
        lines.extend(self._lines)
        if self.status is not None:
            lines.append(f"Run status: {self.status}")
        return "\n".join(lines)


@contextmanager
def run_log_context(capture: RunLogCapture) -> Iterator[None]:
    run_token = current_run_id.set(capture.run_id)
    log_token = _current_run_log.set(capture)
    try:
        yield
    finally:
        _current_run_log.reset(log_token)
        current_run_id.reset(run_token)


def _clean_log_text(value: str) -> str:
    clean = _ANSI_ESCAPE_RE.sub("", value)
    clean = _LOG_MARKUP_RE.sub("", clean)
    return _CONTROL_CHAR_RE.sub("", clean)


def _llm_log_fields(message: str, run_id: str) -> tuple[str, str] | None:
    component, separator, remainder = message.partition(" | ")
    if not separator or component not in _LLM_COMPONENTS:
        return None
    run_field, separator, details = remainder.partition(" | ")
    if not separator or run_field != f"run={run_id}":
        return None
    return component, details


def _capture_llm_filter(record: Mapping[str, object]) -> bool:
    capture = _current_run_log.get()
    message = record.get("message")
    return bool(
        capture is not None
        and not capture.closed
        and current_run_id.get() == capture.run_id
        and isinstance(message, str)
        and _llm_log_fields(message, capture.run_id) is not None
    )


def _capture_llm_record(message: object) -> None:
    capture = _current_run_log.get()
    if capture is None or capture.closed or current_run_id.get() != capture.run_id:
        return
    record = getattr(message, "record", None)
    if not isinstance(record, Mapping):
        return
    body = record.get("message")
    if not isinstance(body, str):
        return
    fields = _llm_log_fields(body, capture.run_id)
    if fields is None:
        return
    component, details = fields
    level = getattr(record.get("level"), "name", "INFO")
    capture.append(str(level), component, details)


def _remove_llm_log_sink() -> None:
    global _LLM_LOG_SINK_ID
    if _LLM_LOG_SINK_ID is not None:
        logger.remove(_LLM_LOG_SINK_ID)
        _LLM_LOG_SINK_ID = None


_run_log_cache = get_cache("zssm_run_logs", str)
_LLM_LOG_SINK_ID: int | None = logger.add(
    _capture_llm_record,
    filter=_capture_llm_filter,
    level="DEBUG",
)
get_driver().on_shutdown(_remove_llm_log_sink)


def append_run_log_event(
    run_id: str,
    level: str,
    component: str,
    message: str,
) -> None:
    capture = _current_run_log.get()
    if (
        capture is None
        or capture.closed
        or capture.run_id != run_id
        or current_run_id.get() != run_id
    ):
        return
    capture.append(level, component, message)


def mark_run_log_status(status: _RunStatus) -> None:
    capture = _current_run_log.get()
    if (
        capture is not None
        and not capture.closed
        and current_run_id.get() == capture.run_id
    ):
        capture.status = status


def run_log_cache_key(
    *,
    bot_id: str,
    adapter_name: str,
    scene_type: str,
    scene_id: str,
    message_id: str,
) -> str:
    """Build an unambiguous cache key for one bot, session, and source message."""

    return json.dumps(
        [bot_id, adapter_name, scene_type, scene_id, message_id],
        ensure_ascii=False,
        separators=(",", ":"),
    )


async def has_run_log(cache_key: str) -> bool:
    return await _run_log_cache.exists(cache_key)


async def get_run_log(cache_key: str) -> str | None:
    return await _run_log_cache.get(cache_key)


async def save_run_log(cache_key: str, capture: RunLogCapture) -> None:
    capture.close()
    try:
        await _run_log_cache.set(cache_key, capture.render_text())
    except asyncio.CancelledError:
        raise
    except Exception as error:
        error.add_note("ZSSM stage: persist bounded invocation logs")
        logger.opt(colors=True).warning(
            f"Failed to cache ZSSM run logs: "
            f"<r>{escape_tag(format_exception(error))}</>"
        )


async def render_run_log(log_text: str) -> bytes:
    rendered = await render_template_html(
        template_path=_TEMPLATE_DIR,
        template_name="run_logs.html.jinja2",
        variables={"log_text": log_text},
    )
    async with get_default_application().extensions.playwright.page(
        viewport={"width": 1120, "height": 900},
        device_scale_factor=2,
    ) as page:
        await page.set_content(rendered.content, wait_until="networkidle")
        if card := await page.query_selector("#card"):
            return await card.screenshot(type="png")
        return await page.screenshot(full_page=True, type="png")


async def safe_render_run_log(log_text: str) -> bytes | None:
    try:
        return await render_run_log(log_text)
    except Exception as error:
        logger.opt(colors=True).warning(
            f"Failed to render ZSSM run logs: "
            f"<r>{escape_tag(format_exception(error))}</>"
        )
        return None


__all__ = [
    "RunLogCapture",
    "append_run_log_event",
    "current_run_id",
    "get_run_log",
    "has_run_log",
    "mark_run_log_status",
    "run_log_cache_key",
    "run_log_context",
    "safe_render_run_log",
    "save_run_log",
]
