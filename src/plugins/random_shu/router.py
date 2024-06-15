from nonebot import get_driver
from nonebot.drivers import URL, ASGIMixin, HTTPServerSetup, Request, Response

from .constant import image_dir, router_path, nonebot_config


async def handle(request: Request) -> Response:
    key = request.url.query.get("key")
    if key is None or not key.endswith(".png"):
        return Response(404, content="Invalid parameter key")
    fp = image_dir / key
    if not fp.exists():
        return Response(404, content="Requested key not exists")
    return Response(
        200,
        headers={"Content-Type": "image/png"},
        content=fp.read_bytes(),
    )


def setup_router():
    assert isinstance((driver := get_driver()), ASGIMixin)
    driver.setup_http_server(
        HTTPServerSetup(
            path=URL(router_path),
            method="GET",
            name="random_shu_image",
            handle_func=handle,
        )
    )
    return URL.build(
        scheme="http",
        host="nbv2",
        port=nonebot_config.port,
        path=router_path,
    )
