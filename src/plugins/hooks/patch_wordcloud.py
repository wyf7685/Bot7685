import functools

from nonebot import require

require("nonebot_plugin_wordcloud")
import nonebot_plugin_wordcloud.data_source as source

original = source._get_wordcloud  # noqa: SLF001  # pyright: ignore[reportPrivateUsage]


@functools.wraps(original)
def _get_wordcloud(messages: list[str], mask_key: str) -> bytes | None:
    gen = (m for m in messages if "当前版本不支持该消息类型" not in m)
    return original(gen, mask_key)  # pyright: ignore[reportArgumentType]


source._get_wordcloud = _get_wordcloud  # noqa: SLF001  # pyright: ignore[reportPrivateUsage]
