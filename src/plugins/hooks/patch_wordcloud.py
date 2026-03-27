from bot7685_ext.nonebot import after_plugin_load
from nonebot import logger
from nonebot.plugin import Plugin

filter_words = {"不支持该消息类型", "当前QQ版本不支持此应用"}


@after_plugin_load
def patch_nbp_wordcloud(plugin: Plugin, exception: Exception | None) -> None:
    if exception is not None or plugin.id_ != "nonebot_plugin_wordcloud":
        return

    import nonebot_plugin_wordcloud.data_source as ds
    from nonebot_plugin_wordcloud.data_source import _get_wordcloud as original

    def _get_wordcloud(messages: list[str], mask_key: str) -> bytes | None:
        gen = (m for m in messages if all(word not in m for word in filter_words))
        return original(iter(gen), mask_key)  # pyright: ignore[reportArgumentType]

    ds._get_wordcloud = _get_wordcloud  # noqa: SLF001
    logger.opt(colors=True).success(
        "Patched <g>nonebot_plugin_wordcloud</g>.<y>_get_wordcloud</y>"
    )
