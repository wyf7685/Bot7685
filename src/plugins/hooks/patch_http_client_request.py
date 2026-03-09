from typing import Protocol, override

import nonebot
from nonebot.drivers import Request, Response
from pydantic import BaseModel


class Config(BaseModel):
    proxy: str | None = None


proxy = nonebot.get_plugin_config(Config).proxy
driver = nonebot.get_driver()
logger = nonebot.logger.opt(colors=True)


class _RequestCall[T](Protocol):
    async def __call__(  # sourcery skip: instance-method-first-arg-name
        self_,  # noqa: N805  # pyright: ignore[reportSelfClsParameterName]
        self: T,
        setup: Request,
    ) -> Response: ...


def patch_request[T](original: _RequestCall[T]) -> _RequestCall[T]:
    @override
    async def request(self: T, setup: Request) -> Response:
        if setup.url.host is not None:
            if setup.url.host == "multimedia.nt.qq.com.cn":
                setup.url = setup.url.with_scheme("http")
                logger.debug(f"Changed scheme to http: <c>{setup.url}</c>")
            elif "wakatime.com" in setup.url.host and proxy is not None:
                setup.proxy = proxy

        return await original(self, setup)

    return request


if "aiohttp" in driver.type:
    from nonebot.drivers.aiohttp import Session as AIOHTTPSession

    AIOHTTPSession.request = patch_request(AIOHTTPSession.request)
    logger.success("Patched <g>AIOHTTPSession</g>.<y>request</y>")

if "httpx" in driver.type:
    from nonebot.drivers.httpx import Session as HTTPXSession

    HTTPXSession.request = patch_request(HTTPXSession.request)
    logger.success("Patched <g>HTTPXSession</g>.<y>request</y>")
