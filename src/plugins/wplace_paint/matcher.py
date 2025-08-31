from typing import Annotated, Literal

import anyio
from nonebot.adapters import Event
from nonebot.params import Depends
from nonebot_plugin_alconna import (
    Alconna,
    Args,
    At,
    CommandMeta,
    MsgTarget,
    Option,
    Subcommand,
    UniMessage,
    on_alconna,
)

from .config import ConfigModel, config
from .fetch import FetchFailed, fetch_me

alc = Alconna(
    "wplace",
    Subcommand(
        "add",
        Option(
            "--notify-mins|-n",
            Args["notify_mins?", int],
            help_text="提前多少分钟通知 (默认10分钟)",
        ),
        alias={"a"},
        help_text="添加一个 WPlace 账号",
    ),
    Subcommand(
        "query",
        Args["target?#查询目标", At | Literal["$group"]],
        alias={"q"},
        help_text="查询目标用户当前绑定的所有账号信息",
    ),
    Subcommand(
        "config",
        Args["identifier#账号标识,ID或用户名", str],
        Option(
            "--notify-mins|-n",
            Args["notify_mins", int],
            help_text="提前多少分钟通知 (默认10分钟)",
        ),
        Option(
            "--set-target",
            help_text="设置当前会话为推送目标",
        ),
        alias={"c"},
        help_text="修改已绑定账号的配置",
    ),
    Subcommand(
        "remove",
        Args["identifier#账号标识,ID或用户名", str],
        alias={"rm"},
        help_text="移除已绑定的账号",
    ),
    meta=CommandMeta(
        description="WPlace 查询",
        usage="wplace <add|query|config|remove> [参数...]",
        author="wyf7685",
    ),
)
matcher = on_alconna(alc)
matcher.shortcut("wpq", {"command": "wplace query {*}"})


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
    token = await prompt("请输入 WPlace Cookies 中的 j (token)")
    cf_clearance = await prompt("请输入 WPlace Cookies 中的 cf_clearance")
    cfg = ConfigModel(
        token=token,
        cf_clearance=cf_clearance,
        target_data=target.dump(),
        user_id=event.get_user_id(),
        notify_mins=notify_mins,
    )

    try:
        resp = await fetch_me(cfg)
    except FetchFailed as e:
        await UniMessage.text(f"验证失败: {e.msg}").finish(at_sender=True)
    except Exception:
        await UniMessage.text("验证时发生意外错误，请稍后再试").finish(at_sender=True)

    cfg.save()
    msg = f"添加成功\n{resp.format_notification()}"
    await UniMessage.text(msg).finish(at_sender=True, reply_to=True)


async def _query_target_cfgs(
    event: Event,
    uni_target: MsgTarget,
    target: At | Literal["$group"] | None = None,
) -> list[ConfigModel]:
    if target == "$group" and uni_target.private:
        await UniMessage.text("请在群聊中使用 $group 参数").finish(reply_to=True)

    if target == "$group":
        cfgs = [cfg for cfg in config.load() if cfg.target.verify(uni_target)]
        if not cfgs:
            await UniMessage.text("群内没有用户绑定推送").finish(reply_to=True)
        return cfgs

    user_id = event.get_user_id() if target is None else target.target
    cfgs = [cfg for cfg in config.load() if cfg.user_id == user_id]
    if not cfgs:
        await UniMessage.text("用户没有绑定任何账号").finish(reply_to=True)
    return cfgs


QueryConfigs = Annotated[list[ConfigModel], Depends(_query_target_cfgs)]


@matcher.assign("~query")
async def assign_query(cfgs: QueryConfigs) -> None:
    async def _fetch(config: ConfigModel) -> None:
        try:
            resp = await fetch_me(config)
            output.append(resp.format_notification())
        except FetchFailed as e:
            output.append(f"查询失败: {e.msg}")
        except Exception as e:
            output.append(f"查询时发生意外错误: {e!r}")

    output = ["查询结果:"]
    async with anyio.create_task_group() as tg:
        for cfg in cfgs:
            tg.start_soon(_fetch, cfg)

    await UniMessage.text("\n\n".join(output)).finish(reply_to=True)


async def _select_cfg(event: Event, identifier: str) -> ConfigModel:
    user_id = event.get_user_id()
    cfgs = [
        cfg
        for cfg in config.load()
        if cfg.user_id == user_id
        and cfg.wp_user_id is not None
        and (str(cfg.wp_user_id) == identifier or cfg.wp_user_name == identifier)
    ]
    if not cfgs:
        await UniMessage.text("未找到对应的绑定账号").finish(at_sender=True)
    return cfgs[0]


SelectedConfig = Annotated[ConfigModel, Depends(_select_cfg)]


@matcher.assign("~config.notify-mins")
async def assign_config_notify_mins(cfg: SelectedConfig, notify_mins: int) -> None:
    cfg.notify_mins = notify_mins
    cfg.save()
    await UniMessage.text(f"将在距离像素回满小于 {notify_mins} 分钟时推送通知").finish(
        at_sender=True, reply_to=True
    )


@matcher.assign("~config.set-target")
async def assign_config_set_target(cfg: SelectedConfig, target: MsgTarget) -> None:
    cfg.target_data = target.dump()
    cfg.save()
    await UniMessage.text("已设置当前会话为推送目标").finish(
        at_sender=True, reply_to=True
    )


@matcher.assign("~remove")
async def assign_remove(cfg: SelectedConfig) -> None:
    config.remove(lambda c: c is cfg)
    await UniMessage.text(f"移除成功: {cfg.wp_user_name}(ID: {cfg.wp_user_id})").finish(
        at_sender=True, reply_to=True
    )
