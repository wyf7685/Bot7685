from bot7685_ext.nonebot import on_plugin_load
from nonebot import get_plugin_config, logger
from nonebot.plugin import Plugin
from pydantic import BaseModel

from src.utils import copy_signature


class Config(BaseModel):
    wordcloud_filter_words: set[str] = set()


@on_plugin_load("after", plugin_id="nonebot_plugin_wordcloud", skip_on_exc=True)
def patch_nbp_wordcloud(_: Plugin | None = None) -> None:
    filter_words = get_plugin_config(Config).wordcloud_filter_words
    if not filter_words:
        return

    import nonebot_plugin_wordcloud.data_source as ds_mod
    from nonebot_plugin_wordcloud.data_source import _get_wordcloud as original

    @copy_signature(original)
    def _get_wordcloud(messages: list[str], mask_key: str) -> bytes | None:
        gen = (m for m in messages if all(word not in m for word in filter_words))
        return original(iter(gen), mask_key)  # ty:ignore[invalid-argument-type]

    ds_mod._get_wordcloud = _get_wordcloud  # noqa: SLF001
    logger.opt(colors=True).success(
        "Patched <g>nonebot_plugin_wordcloud</g>.<y>_get_wordcloud</y>"
    )
