import http
import inspect
import logging
import logging.config
from copy import copy
from typing import ClassVar, cast, override

from .ansi_to_tag import ansi_to_tag
from .config import escape_tag, logger


# https://loguru.readthedocs.io/en/stable/overview.html#entirely-compatible-with-standard-logging
class LoguruHandler(logging.Handler):  # pragma: no cover
    """logging 与 loguru 之间的桥梁，将 logging 的日志转发到 loguru。"""

    def use_colors(self) -> bool:
        return False

    @override
    def emit(self, record: logging.LogRecord) -> None:
        try:
            level = logger.level(record.levelname).name
        except ValueError:
            level = record.levelno

        frame, depth = inspect.currentframe(), 0
        while frame and (
            depth == 0 or frame.f_code.co_filename in {logging.__file__, __file__}
        ):
            frame = frame.f_back
            depth += 1

        logger.opt(
            depth=depth, colors=self.use_colors(), exception=record.exc_info
        ).log(level, record.getMessage())


class UvicornDefaultHandler(LoguruHandler):
    @override
    def use_colors(self) -> bool:
        return True

    @override
    def emit(self, record: logging.LogRecord) -> None:
        if "color_message" in record.__dict__:
            color_message = record.__dict__["color_message"]
            record.msg = ansi_to_tag(color_message)
        super().emit(record)


class UvicornAccessHandler(LoguruHandler):
    status_code_colors: ClassVar[dict[int, str]] = {
        1: "light-white",
        2: "green",
        3: "yellow",
        4: "red",
        5: "light-red",
    }

    @override
    def use_colors(self) -> bool:
        return True

    @classmethod
    def get_status_code(cls, status_code: int) -> str:
        try:
            status_phrase = http.HTTPStatus(status_code).phrase
        except ValueError:
            status_phrase = ""
        status_and_phrase = escape_tag(f"{status_code} {status_phrase}")
        if status_code // 100 in cls.status_code_colors:
            color = cls.status_code_colors[status_code // 100]
            status_and_phrase = f"<{color}>{status_and_phrase}</>"
        return status_and_phrase

    @override
    def emit(self, record: logging.LogRecord) -> None:
        recordcopy = copy(record)
        (
            client_addr,
            method,
            full_path,
            http_version,
            status_code,
        ) = cast("tuple[str, str, str, str, int]", recordcopy.args)
        status_code = self.get_status_code(int(status_code))
        request_line = f"{method} {full_path} HTTP/{http_version}"
        formatted = (
            f"{escape_tag(client_addr)} "
            f'"<bold>{escape_tag(request_line)}</>" {status_code}'
        )
        recordcopy.msg = formatted
        recordcopy.args = ()
        super().emit(recordcopy)


LOGGING_CONFIG = {
    "version": 1,
    "disable_existing_loggers": False,
    "handlers": {
        "default": {"class": f"{__name__}.LoguruHandler"},
        "uvicorn": {"class": f"{__name__}.UvicornDefaultHandler"},
        "uvicorn.access": {"class": f"{__name__}.UvicornAccessHandler"},
    },
    "loggers": {
        "uvicorn": {"handlers": ["uvicorn"], "level": "INFO", "propagate": False},
        "uvicorn.error": {"level": "INFO"},
        "uvicorn.access": {
            "handlers": ["uvicorn.access"],
            "level": "INFO",
            "propagate": False,
        },
        "httpx": {"handlers": ["default"], "level": "INFO", "propagate": False},
    },
}


def configure_logging() -> None:
    """配置日志记录器。"""
    logging.config.dictConfig(LOGGING_CONFIG)
