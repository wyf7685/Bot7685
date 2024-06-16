from nonebot import get_driver
from nonebot.drivers import URL, ASGIMixin, HTTPServerSetup, Request, Response
from nonebot.log import logger

from .constant import image_dir, image_text, nonebot_config, router_path


async def handle(request: Request) -> Response:
    key = request.url.query.get("key")
    if key is None or not key.endswith(".png"):
        return Response(404, content="Invalid parameter key")
    fp = image_dir / key
    if not fp.exists():
        return Response(404, content="Requested key not exists")

    image_text.get(fp.stem, "黍泡泡")
    logger.info(f"黍泡泡抽取结果: {fp.name} - {image_text.get(fp.stem, '黍泡泡')}")
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
