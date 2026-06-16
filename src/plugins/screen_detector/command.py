import contextlib
from datetime import UTC, datetime, timedelta

from nonebot import logger
from nonebot_plugin_alconna import (
    Alconna,
    Args,
    MsgTarget,
    Subcommand,
    SupportScope,
    Target,
    UniMessage,
    message_reaction,
    on_alconna,
)

from src.plugins.upload_cos import upload_cos

from .api import detector_client
from .config import pkg_subs

alc = Alconna(
    "detector",
    Subcommand("package", Args["duration", r"re:\d+[smhd]"]),
    Subcommand("subscribe"),
    Subcommand("unsubscribe"),
)
matcher = on_alconna(alc)


@matcher.assign("~package")
async def assign_package(duration: str, target: MsgTarget) -> None:
    mode = duration[-1]
    num = int(duration[:-1])
    kwd = {"s": "seconds", "m": "minutes", "h": "hours", "d": "days"}[mode]
    delta = timedelta(**{kwd: num})

    since = (datetime.now() - delta).astimezone(UTC)
    path = await detector_client.package(since)
    if path is None:
        await UniMessage.text("打包检测结果失败").finish()
    size = path.stat().st_size / 1024 / 1024
    logger.opt(colors=True).info(f"文件大小: <c>{size:.3f}</> MB")

    if target.scope == SupportScope.qq_client:
        with contextlib.suppress(Exception):
            await message_reaction("124")  # OK

    cos_key = f"detector/package-{datetime.now():%Y-%m-%d_%H-%M-%S}.zip"
    try:
        url = await upload_cos(path, key=cos_key)
    except Exception:
        logger.exception("上传打包结果失败")
        await UniMessage.text("上传打包结果失败").finish()

    await UniMessage.text(f"打包完成:\n{url}").finish()


@matcher.assign("~subscribe")
async def assign_subscribe(target: MsgTarget) -> None:
    subs = pkg_subs.load()
    if any(target.verify(Target.load(sub)) for sub in subs):
        await UniMessage.text("当前会话已订阅打包结果").finish()
    subs.append(target.dump())
    pkg_subs.save(subs)
    await UniMessage.text("订阅成功").finish()


@matcher.assign("~unsubscribe")
async def assign_unsubscribe(target: MsgTarget) -> None:
    pkg_subs.save(
        [sub for sub in pkg_subs.load() if not target.verify(Target.load(sub))]
    )
    await UniMessage.text("退订成功").finish()
