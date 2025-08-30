import anyio
from nonebot.adapters import Event
from nonebot_plugin_alconna import (
    Alconna,
    Args,
    MsgTarget,
    Option,
    Subcommand,
    UniMessage,
    on_alconna,
)

from .config import ConfigModel, config
from .fetch import FetchFailed, fetch_me_with_async_playwright

alc = Alconna(
    "wplace",
    Subcommand(
        "add",
        Option(
            "--notify_mins|-n",
            Args["notify_mins?", int],
            help_text="提前多少分钟通知 (默认10分钟)",
        ),
        help_text="添加一个用户 (token 和 cf_clearance 可在网页端 Cookies 中找到)",
    ),
    Subcommand("query", help_text="查询当前绑定的所有用户信息"),
)

matcher = on_alconna(alc)


async def prompt(msg: str) -> str:
    resp = await matcher.prompt(msg + "\n(回复 “取消” 以取消操作)")
    if resp is None:
        await UniMessage.text("操作已取消").finish(at_sender=True)
    text = resp.extract_plain_text().strip()
    if text == "取消":
        await UniMessage.text("操作已取消").finish(at_sender=True)
    return text


@matcher.assign("~add")
async def assign_add(
    event: Event,
    target: MsgTarget,
    notify_mins: int = 10,
) -> None:
    token = await prompt("请输入 WPlace 的 token (Cookies 中的 j)")
    cf_clearance = await prompt("请输入 wplace.live Cookies 中的 cf_clearance")

    try:
        await fetch_me_with_async_playwright(token, cf_clearance)
    except FetchFailed as e:
        await UniMessage.text(f"验证失败: {e.msg}").finish(at_sender=True)
    except Exception:
        await UniMessage.text("验证时发生意外错误，请稍后再试").finish(at_sender=True)

    cfg = ConfigModel(
        token=token,
        cf_clearance=cf_clearance,
        target_data=target.dump(),
        user_id=event.get_user_id(),
        notify_mins=notify_mins,
    )
    config.add(cfg)
    await UniMessage.text("添加成功").finish(at_sender=True)


async def _fetch(config: ConfigModel, output: list[str]) -> None:
    try:
        resp = await fetch_me_with_async_playwright(config.token, config.cf_clearance)
        output.append(resp.format_notification())
    except FetchFailed as e:
        output.append(f"查询失败: {e.msg}\n")
    except Exception as e:
        output.append(f"查询时发生意外错误: {e!r}")


@matcher.assign("~query")
async def assign_query(event: Event) -> None:
    user_id = event.get_user_id()
    cfgs = [cfg for cfg in config.load() if cfg.user_id == user_id]
    if not cfgs:
        await UniMessage.text("你还没有绑定任何用户").finish(at_sender=True)

    output = ["查询结果:"]
    async with anyio.create_task_group() as tg:
        for cfg in cfgs:
            tg.start_soon(_fetch, cfg, output)

    await UniMessage.text("\n\n".join(output)).finish(at_sender=True)
