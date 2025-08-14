# ruff: noqa: SLF001
import nonebot


@nonebot.get_driver().on_startup
def _() -> None:
    try:
        nonebot.require("nonebot_plugin_wordcloud")
        import nonebot_plugin_wordcloud.data_source as source
    except (ImportError, RuntimeError):
        return

    def _get_wordcloud(messages: list[str], mask_key: str) -> bytes | None:
        gen = (m for m in messages if "不支持该消息类型" not in m)
        return original(iter(gen), mask_key)  # pyright: ignore[reportArgumentType]

    original = source._get_wordcloud  # pyright: ignore[reportPrivateUsage]
    source._get_wordcloud = _get_wordcloud  # pyright: ignore[reportPrivateUsage]

    @nonebot.get_driver().on_shutdown
    def _() -> None:
        source._get_wordcloud = original
