import contextlib
from typing import Protocol, override

import nonebot
from nonebot.drivers import Request, Response
from pydantic import BaseModel


class Config(BaseModel):
    http_proxy: str | None = None


config = nonebot.get_plugin_config(Config)
driver = nonebot.get_driver()
logger = nonebot.logger.opt(colors=True)


class _RequestCall[T](Protocol):
    async def __call__(  # sourcery skip: instance-method-first-arg-name
        self_,  # noqa: N805  # type: ignore[]
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
            elif "wakatime.com" in setup.url.host and config.http_proxy is not None:
                setup.proxy = config.http_proxy

        return await original(self, setup)

    return request


with contextlib.suppress(ImportError):
    from nonebot.drivers.aiohttp import Session as AIOHTTPSession

    AIOHTTPSession.request = patch_request(AIOHTTPSession.request)
    logger.success("Patched AIOHTTPSession.request")

with contextlib.suppress(ImportError):
    from nonebot.drivers.httpx import Session as HTTPXSession

    HTTPXSession.request = patch_request(HTTPXSession.request)
    logger.success("Patched HTTPXSession.request")
