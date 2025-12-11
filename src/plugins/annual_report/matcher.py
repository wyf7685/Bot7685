from nonebot import logger
from nonebot_plugin_alconna import Alconna, Args, CommandMeta, UniMessage, on_alconna
from nonebot_plugin_uninfo import Uninfo

from .analyzer import ChatAnalyzer
from .db_converter import fetch_analyzer_input
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
async def _(session: Uninfo, year: int | None = None) -> None:
    analyzer_input = await fetch_analyzer_input(session, year)

    try:
        analyzer = ChatAnalyzer(analyzer_input)
        analyzer.analyze()
        generator = ImageGenerator(analyzer)
        image_bytes = await generator.generate()
    except Exception as e:
        logger.exception("生成年度报告失败")
        await matcher.finish(f"生成年度报告失败: {e}")

    if image_bytes is None:
        await matcher.finish("生成年度报告失败")

    await UniMessage.image(raw=image_bytes).finish()
