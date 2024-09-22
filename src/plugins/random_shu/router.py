from nonebot import get_driver
from nonebot.drivers import URL, ASGIMixin, HTTPServerSetup, Request, Response
from nonebot.log import logger

from .constant import router_path
from .data import Data


async def handle(request: Request) -> Response:
    key = request.url.query.get("key")
    if key is None or not key.endswith(".png"):
        return Response(status_code=404, content="Invalid parameter key")
    if (item := await Data.find(key)) is None:
        return Response(status_code=404, content="Requested key not exists")

    logger.info(f"黍泡泡抽取结果: {item.name} - {item.text}")
    return Response(
        status_code=200,
        headers={"Content-Type": "image/png"},
        content=item.path.read_bytes(),
    )


def setup_router() -> URL:
    driver = get_driver()
    assert isinstance(driver, ASGIMixin)  # noqa: S101
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
        host="bot7685",
        port=driver.config.port,
        path=router_path,
    )
