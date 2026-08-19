from typing import TYPE_CHECKING, Any

from bot7685_ext.nonebot import on_plugin_load
from nonebot import logger

from src.utils import copy_signature

if TYPE_CHECKING:
    from playwright.async_api import Browser, BrowserType


async def _patched_connect(browser_type: str, **kwargs: Any) -> Browser:
    from nonebot_plugin_htmlrender.browser import _playwright
    from nonebot_plugin_htmlrender.config import plugin_config

    if _playwright is None:
        raise RuntimeError("Playwright 未初始化")
    if (endpoint := plugin_config.htmlrender_connect) is None:
        raise RuntimeError("未配置 htmlrender_connect")

    browser: BrowserType = getattr(_playwright, browser_type)
    logger.opt(depth=1).info(
        f"正在使用 Playwright 协议连接 {browser_type} ({endpoint})"
    )
    return await browser.connect(endpoint, **kwargs)


@on_plugin_load("after", plugin_id="nonebot_plugin_htmlrender", skip_on_exc=True)
def _patch_htmlrender_connect(_: object) -> None:
    from importlib.metadata import version

    htmlrender_version = version("nonebot_plugin_htmlrender")
    if htmlrender_version != "0.6.7":
        return

    from nonebot_plugin_htmlrender import browser as browser_mod

    browser_mod._connect = copy_signature(browser_mod._connect)(_patched_connect)  # noqa: SLF001
