from typing import Protocol, override

import nonebot
from nonebot.drivers import HTTPClientMixin, Request, Response
from pydantic import BaseModel

from src.utils import copy_signature

from ._http_request import set_request_preprocessor


class Config(BaseModel):
    proxy: str | None = None


proxy = nonebot.get_plugin_config(Config).proxy
driver = nonebot.get_driver()
logger = nonebot.logger.opt(colors=True)


class _RequestCall[T](Protocol):
    async def __call__(__self, self: T, setup: Request) -> Response: ...  # noqa: N805


def prepare_request(setup: Request) -> None:
    if (host := setup.url.host) is None:
        return

    if host == "multimedia.nt.qq.com.cn":
        if setup.url.scheme != "http":
            setup.url = setup.url.with_scheme("http")
            logger.debug(f"Changed scheme to http: <c>{setup.url}</c>")
    elif (
        host == "wakatime.com" or host.endswith(".wakatime.com")
    ) and proxy is not None:
        setup.proxy = proxy


def patch_request[T](original: _RequestCall[T]) -> _RequestCall[T]:
    @override
    async def request(self: T, setup: Request) -> Response:
        prepare_request(setup)
        return await original(self, setup)

    return request


set_request_preprocessor(driver, prepare_request)

if isinstance(driver, HTTPClientMixin):
    driver_type = type(driver)
    driver_type.request = copy_signature(
        driver_type.request,
        patch_request(driver_type.request),
    )
    logger.success(f"Patched <g>{driver_type.__name__}</g>.<y>request</y>")


if "aiohttp" in driver.type:
    from nonebot.drivers.aiohttp import Session as AIOHTTPSession

    AIOHTTPSession.request = copy_signature(
        AIOHTTPSession.request,
        patch_request(AIOHTTPSession.request),
    )
    logger.success("Patched <g>AIOHTTPSession</g>.<y>request</y>")

if "httpx" in driver.type:
    from nonebot.drivers.httpx import Session as HTTPXSession

    HTTPXSession.request = copy_signature(
        HTTPXSession.request,
        patch_request(HTTPXSession.request),
    )
    logger.success("Patched <g>HTTPXSession</g>.<y>request</y>")
