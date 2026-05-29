from datetime import UTC, datetime, timedelta

from nonebot_plugin_alconna import Alconna, Args, Subcommand, UniMessage, on_alconna

from .api import detector_client

alc = Alconna("detector", Subcommand("package", Args["duration", r"re:\d+[smhd]"]))
matcher = on_alconna(alc)


@matcher.assign("~package")
async def assign_package(duration: str) -> None:
    mode = duration[-1]
    num = int(duration[:-1])
    kwd = {"s": "seconds", "m": "minutes", "h": "hours", "d": "days"}[mode]
    delta = timedelta(**{kwd: num})

    since = (datetime.now() - delta).astimezone(UTC)

    raw = await detector_client.package(since)
    if raw is None:
        await UniMessage.text("打包检测结果失败").finish()

    filename = f"detector_package_{datetime.now():%Y-%m-%d_%H-%M-%S}.zip"
    await UniMessage.file(raw=raw, name=filename).finish()
