import contextlib
from typing import Protocol, override

from nonebot import get_driver
from nonebot.drivers import HTTPClientMixin, Request, Response


class _RequestCall[M: HTTPClientMixin](Protocol):
    async def __call__(  # sourcery skip: instance-method-first-arg-name
        self_,  # pyright:ignore[reportSelfClsParameterName]  # noqa: N805
        self: M,
        setup: Request,
    ) -> Response: ...


def patch_request[M: HTTPClientMixin](original: _RequestCall[M]) -> _RequestCall[M]:
    @override
    async def request(self: M, setup: Request) -> Response:
        if setup.url.host == "multimedia.nt.qq.com.cn":
            setup.url.scheme = "http"

        return await original(self, setup)

    return request


with contextlib.suppress(ImportError):
    from nonebot.drivers.aiohttp import Mixin as AIOHTTPMixin

    if issubclass(cls := get_driver().__class__, AIOHTTPMixin):
        cls.request = patch_request(cls.request)

with contextlib.suppress(ImportError):
    from nonebot.drivers.httpx import Mixin as HTTPXMixin

    if issubclass(cls := get_driver().__class__, HTTPXMixin):
        cls.request = patch_request(cls.request)
