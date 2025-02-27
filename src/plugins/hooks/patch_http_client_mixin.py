import contextlib
from typing import Protocol, override

import nonebot
from nonebot.drivers import HTTPClientMixin, Request, Response
from pydantic import BaseModel


class Config(BaseModel):
    http_proxy: str | None = None


config = nonebot.get_plugin_config(Config)
driver = nonebot.get_driver()
logger = nonebot.logger.opt(colors=True)


class _RequestCall[M: HTTPClientMixin](Protocol):
    async def __call__(self, setup: Request) -> Response: ...


def patch_request[M: HTTPClientMixin](original: _RequestCall[M]) -> _RequestCall[M]:
    @override
    async def request(setup: Request) -> Response:
        if setup.url.host is not None:
            if setup.url.host == "multimedia.nt.qq.com.cn":
                setup.url = setup.url.with_scheme("http")
                logger.debug(f"Changed scheme to http: <c>{setup.url}</c>")
            elif "wakatime.com" in setup.url.host and config.http_proxy is not None:
                setup.proxy = config.http_proxy

        return await original(setup)

    return request


with contextlib.suppress(ImportError):
    from nonebot.drivers.aiohttp import Mixin as AIOHTTPMixin

    if isinstance(driver, AIOHTTPMixin):
        driver.request = patch_request(driver.request)
        logger.success("Patched AIOHTTPMixin.request")

with contextlib.suppress(ImportError):
    from nonebot.drivers.httpx import Mixin as HTTPXMixin

    if isinstance(driver, HTTPXMixin):
        driver.request = patch_request(original=driver.request)
        logger.success("Patched HTTPXMixin.request")
