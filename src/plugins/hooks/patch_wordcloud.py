from bot7685_ext.nonebot import on_plugin_load
from nonebot import get_plugin, get_plugin_config, logger
from nonebot.plugin import Plugin
from pydantic import BaseModel


class Config(BaseModel):
    wordcloud_filter_words: set[str] = set()


if filter_words := get_plugin_config(Config).wordcloud_filter_words:

    @on_plugin_load("after", plugin_id="nonebot_plugin_wordcloud", skip_on_exc=True)
    def patch_nbp_wordcloud(_: Plugin) -> None:
        import nonebot_plugin_wordcloud.data_source as ds
        from nonebot_plugin_wordcloud.data_source import _get_wordcloud as original

        def _get_wordcloud(messages: list[str], mask_key: str) -> bytes | None:
            gen = (m for m in messages if all(word not in m for word in filter_words))
            return original(iter(gen), mask_key)  # pyright: ignore[reportArgumentType]

        ds._get_wordcloud = _get_wordcloud  # noqa: SLF001
        logger.opt(colors=True).success(
            "Patched <g>nonebot_plugin_wordcloud</g>.<y>_get_wordcloud</y>"
        )

    if plugin := get_plugin("nonebot_plugin_wordcloud"):
        patch_nbp_wordcloud(plugin)
