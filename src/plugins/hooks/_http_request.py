from collections.abc import Callable
from typing import cast

from nonebot.drivers import Driver, Request

_PREPROCESSOR_ATTR = "_bot7685_http_request_preprocessor"

type RequestPreprocessor = Callable[[Request], None]


def set_request_preprocessor(
    driver: Driver,
    preprocessor: RequestPreprocessor,
) -> None:
    setattr(driver, _PREPROCESSOR_ATTR, preprocessor)


def preprocess_request(driver: Driver, setup: Request) -> None:
    preprocessor = cast(
        "RequestPreprocessor | None",
        getattr(driver, _PREPROCESSOR_ATTR, None),
    )
    if preprocessor is not None:
        preprocessor(setup)
