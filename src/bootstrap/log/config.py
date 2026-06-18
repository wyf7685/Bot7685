import functools
import re
import sys
from collections.abc import Callable

import loguru

logger: loguru.Logger = loguru.logger


def escape_tag(s: str) -> str:
    """用于记录带颜色日志时转义 `<tag>` 类型特殊标签

    参考: [loguru color 标签](https://loguru.readthedocs.io/en/stable/api/logger.html#color)

    参数:
        s: 需要转义的字符串
    """
    return re.sub(r"</?((?:[fb]g\s)?[^<>\s]*)>", r"\\\g<0>", s)


log_format = (
    "<g>{time:HH:mm:ss}</g> [<lvl>{level}</lvl>] <c><u>{name}</u></c> | {message}"
)
_log_level = "DEBUG"


@functools.cache
def _get_log_level_no() -> int:
    return logger.level(_log_level).no


def set_log_level(level: str) -> None:
    global _log_level
    _log_level = level
    _get_log_level_no.cache_clear()


def log_level_filter() -> Callable[[loguru.Record], bool]:
    def filter_func(record: loguru.Record) -> bool:
        try:
            return record["level"].no >= _get_log_level_no()
        except Exception:
            return True

    return filter_func


_HIDDEN_NAMES = ("uvicorn", "starlette", "httpx")


def _hide_upstream(record: loguru.Record) -> None:
    if (name := record["name"]) is None:
        return

    for hidden_name in _HIDDEN_NAMES:
        if name.startswith(hidden_name):
            record["name"] = hidden_name
            return


logger.remove()
logger.configure(patcher=_hide_upstream)

stdout_log_id = None
if sys.stdout:
    stdout_log_id = logger.add(
        sys.stdout,
        level="TRACE",
        diagnose=False,
        enqueue=True,
        format=log_format,
        filter=log_level_filter(),
    )

file_log_id = logger.add(
    "./logs/{time:YYYY-MM-DD}.log",
    rotation="00:00",
    level="DEBUG",
    colorize=True,
    diagnose=True,
    enqueue=True,
    format=log_format,
    encoding="utf-8",
)
