# ruff: noqa: SLF001

from nonebot import require

require("nonebot_plugin_wordcloud")
import nonebot
import nonebot_plugin_wordcloud.data_source as source

original = source._get_wordcloud  # pyright: ignore[reportPrivateUsage]


def _get_wordcloud(messages: list[str], mask_key: str) -> bytes | None:
    gen = (m for m in messages if "当前版本不支持该消息类型" not in m)
    return original(gen, mask_key)  # pyright: ignore[reportArgumentType]


@nonebot.get_driver().on_startup
def patch() -> None:
    source._get_wordcloud = _get_wordcloud  # pyright: ignore[reportPrivateUsage]


@nonebot.get_driver().on_shutdown
def dispose() -> None:
    source._get_wordcloud = original  # pyright: ignore[reportPrivateUsage]
