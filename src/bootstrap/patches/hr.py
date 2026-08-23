from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import TYPE_CHECKING, Any, Literal

from bot7685_ext.nonebot import on_plugin_load
from nonebot import logger

if TYPE_CHECKING:
    from playwright.async_api import Browser, BrowserType, Page


def _hr_version() -> tuple[int, ...]:
    import importlib.metadata

    try:
        version = importlib.metadata.version("nonebot_plugin_htmlrender")
    except importlib.metadata.PackageNotFoundError as e:
        raise RuntimeError("未安装 nonebot_plugin_htmlrender") from e
    return tuple(map(int, version.split(".")))


async def _patched_connect(browser_type: str, **kwargs: Any) -> Browser:
    from nonebot_plugin_htmlrender import browser, config  # ty: ignore[unresolved-import]  # noqa: I001

    if (pw := browser._playwright) is None:  # noqa: SLF001
        raise RuntimeError("Playwright 未初始化")
    if (endpoint := config.plugin_config.htmlrender_connect) is None:
        raise RuntimeError("未配置 htmlrender_connect")
    kwargs.pop("endpoint", None)
    kwargs.pop("ws_endpoint", None)

    browser: BrowserType = getattr(pw, browser_type)
    logger.opt(depth=1).info(
        f"正在使用 Playwright 协议连接 {browser_type} ({endpoint})"
    )
    return await browser.connect(endpoint, **kwargs)


@asynccontextmanager
async def _get_new_page(
    device_scale_factor: float = 2,
    **kwargs: Any,
) -> AsyncGenerator[Page]:
    import nonebot_plugin_htmlrender as hr_mod

    # 0.8.x
    if hasattr(hr_mod, "get_default_application"):
        application = hr_mod.get_default_application()
        try:
            extension = application.extensions.playwright
        except Exception:
            raise RuntimeError(
                "The htmlrender playwright provider is not available; "
                "install `nonebot-plugin-htmlrender[playwright]`."
            ) from None
        async with extension.page(
            device_scale_factor=device_scale_factor, **kwargs
        ) as page:
            yield page
    # 0.7.x
    elif hasattr(hr_mod, "get_render_context"):
        async with hr_mod.get_render_context(
            device_scale_factor=device_scale_factor, **kwargs
        ) as page:
            yield page
    else:
        raise RuntimeError("Unsupported version of nonebot_plugin_htmlrender")


async def _template_to_html(
    template_path: str,
    template_name: str,
    filters: dict[str, Any] | None = None,
    **kwargs: Any,
) -> str:
    from nonebot_plugin_htmlrender import render_template_html

    rendered = await render_template_html(
        template_path=template_path,
        template_name=template_name,
        variables=kwargs,
        filters=filters,
    )
    return rendered.content


async def _html_to_pic(
    html: str,
    wait: int = 0,
    template_path: str = f"file://{Path.cwd()}",
    type: Literal["jpeg", "png"] = "png",  # noqa: A002
    quality: int | None = None,
    device_scale_factor: float = 2,
    screenshot_timeout: float | None = 30_000,
    full_page: bool | None = True,
    **kwargs: Any,
) -> bytes:
    del wait, full_page, kwargs  # Unused

    from nonebot_plugin_htmlrender import render_html

    rendered = await render_html(
        html=html,
        device_pixel_ratio=device_scale_factor,
        image_format=type,
        quality=quality,
        base_url=template_path,
        timeout_seconds=screenshot_timeout / 1000 if screenshot_timeout else None,
    )
    return rendered.data


async def _template_to_pic(
    template_path: str,
    template_name: str,
    templates: dict[Any, Any],
    filters: dict[str, Any] | None = None,
    pages: dict[Any, Any] | None = None,
    wait: int = 0,
    type: Literal["jpeg", "png"] = "png",  # noqa: A002
    quality: int | None = None,
    device_scale_factor: float = 2,
    screenshot_timeout: float | None = 30_000,
) -> bytes:
    del wait, pages  # Unused

    from nonebot_plugin_htmlrender import render_template

    rendered = await render_template(
        template_path=template_path,
        template_name=template_name,
        variables=templates,
        filters=filters,
        device_pixel_ratio=device_scale_factor,
        image_format=type,
        quality=quality,
        timeout_seconds=screenshot_timeout / 1000 if screenshot_timeout else None,
    )
    return rendered.data


@on_plugin_load("after", plugin_id="nonebot_plugin_htmlrender", skip_on_exc=True)
def patch_htmlrender(_: object) -> None:
    version = _hr_version()

    if version == (0, 6, 7):
        import nonebot_plugin_htmlrender.browser as browser_mod  # ty: ignore[unresolved-import]

        setattr(browser_mod, "_connect", _patched_connect)  # noqa: B010

    if (0, 7, 0) <= version < (0, 9, 0):
        import nonebot_plugin_htmlrender as hr_mod

        setattr(hr_mod, "get_new_page", _get_new_page)  # noqa: B010
        if version >= (0, 8, 0):
            setattr(hr_mod, "template_to_html", _template_to_html)  # noqa: B010
            setattr(hr_mod, "html_to_pic", _html_to_pic)  # noqa: B010
            setattr(hr_mod, "template_to_pic", _template_to_pic)  # noqa: B010
