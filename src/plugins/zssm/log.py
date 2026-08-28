import re
from contextvars import ContextVar

from nonebot import logger
from nonebot.utils import escape_tag

from src.service.llm import LLMServiceError


def safe_log_text(value: object, limit: int = 80) -> str:
    compact = re.sub(r"\s+", " ", str(value)).strip()
    return escape_tag(compact[:limit] or "none")


def cause_name(error: BaseException) -> str:
    if isinstance(error, LLMServiceError) and error.cause is not None:
        return type(error.cause).__name__
    return type(error).__name__


current_run_id: ContextVar[str | None] = ContextVar("current_run_id", default=None)


def log_event(
    level: str,
    component: str,
    message: str,
) -> None:
    run_id = current_run_id.get()
    if run_id is None:
        return
    run = safe_log_text(run_id, 32)
    logger.opt(colors=True).log(
        level,
        f"<m>{component}</m> | run=<c>{run}</> | {message}",
    )


__all__ = ["cause_name", "log_event", "safe_log_text"]
