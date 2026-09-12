import anyio.to_thread
from nonebot import logger
from nonebot.adapters import Bot
from nonebot_plugin_alconna import Alconna, Args, CommandMeta, UniMessage, on_alconna
from nonebot_plugin_uninfo import Uninfo

from .analyzer import ChatAnalyzer
from .db_converter import stream_analyzer_messages
from .image_generator import ImageGenerator

matcher = on_alconna(
    Alconna(
        "annual_report",
        Args["year?#年份", int],
        meta=CommandMeta(
            description="生成年度报告",
            usage="annual_report [年份]",
            author="wyf7685",
        ),
    ),
    aliases={"年度报告"},
)


@matcher.handle()
async def _(bot: Bot, session: Uninfo, year: int | None = None) -> None:
    analyzer = ChatAnalyzer(session.scene.name or session.id)
    image_bytes: bytes | None = None

    try:
        async for batch in stream_analyzer_messages(bot, session, year):
            await anyio.to_thread.run_sync(analyzer.consume_batch, batch)

        if analyzer.message_count:
            await anyio.to_thread.run_sync(analyzer.finalize)
            image_bytes = await ImageGenerator(analyzer).generate()
    except Exception as error:
        logger.exception("生成年度报告失败")
        await matcher.finish(f"生成年度报告失败: {error}")

    if analyzer.message_count == 0:
        await matcher.finish("未找到该年度的群聊记录")
    if image_bytes is None:
        await matcher.finish("生成年度报告失败")

    await UniMessage.image(raw=image_bytes).finish()
