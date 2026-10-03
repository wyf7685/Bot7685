import re

from nonebot import logger
from nonebot.utils import escape_tag

from src.utils import format_exception

from .run_logs import append_run_log_event, current_run_id


def safe_log_text(value: object, limit: int = 80) -> str:
    compact = re.sub(r"\s+", " ", str(value)).strip()
    return escape_tag(compact[:limit] or "none")


def error_context(error: BaseException | None) -> str:
    """Return bounded diagnostics safe to include in a colored log message."""

    return escape_tag(format_exception(error))


def log_event(
    level: str,
    component: str,
    message: str,
) -> None:
    run_id = current_run_id.get()
    if run_id is None:
        return
    append_run_log_event(run_id, level, component, message)
    run = safe_log_text(run_id, 32)
    logger.opt(colors=True).log(
        level,
        f"<m>{component}</m> | run=<c>{run}</> | {message}",
    )


__all__ = ["error_context", "log_event", "safe_log_text"]
