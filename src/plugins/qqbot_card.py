import asyncio
import hashlib
import json
from typing import Any, Literal

from nonebot import get_driver, on_message
from nonebot.adapters.onebot.v11 import PrivateMessageEvent
from nonebot.drivers import URL, ASGIMixin, HTTPServerSetup, Request, Response

router_path = "/qqbot_card"
_key: str = ""
_data: dict[str, dict[str, Any]] = {}
_future: dict[str, asyncio.Future[str]] = {}


async def get_json_card(type: Literal["embed", "ark"], data: dict[str, Any]) -> str:
    h = hashlib.sha256()
    h.update(type.encode())
    h.update(repr(data).encode())
    key = h.hexdigest()

    loop = asyncio.get_running_loop()
    _data[key] = {"type": type, "data": data}
    fut = _future[key] = loop.create_future()

    def clean():
        if key in _data:
            del _data[key]
        if not fut.done():
            fut.set_exception(TimeoutError("json卡片获取超时"))
        if key in _future:
            del _future[key]

    loop.call_later(20, clean)
    return await fut


async def handle(request: Request) -> Response:
    key = (request.data or {}).get("key", None)
    if isinstance(key, str) and key in _data:
        global _key
        _key = key
        return Response(
            status_code=200,
            headers={"Content-Type": "application/json"},
            content=json.dumps(_data[key]),
        )
    return Response(404)


def setup_router():
    assert isinstance((driver := get_driver()), ASGIMixin)
    driver.setup_http_server(
        HTTPServerSetup(
            path=URL(router_path),
            method="POST",
            name="qqbot_card",
            handle_func=handle,
        )
    )


def _rule(event: PrivateMessageEvent) -> bool:
    return bool(_key and event.user_id == 0)


@on_message(_rule).handle()
async def _(event: PrivateMessageEvent):
    global _key
    msg = event.get_message().include("json")
    if not msg:
        return
    _future[_key].set_result(msg[0].data["data"])
    _key = ""


setup_router()
