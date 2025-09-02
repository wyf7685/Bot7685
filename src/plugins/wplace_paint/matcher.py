from typing import Annotated, Literal, NoReturn

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
from .fetch import RequestFailed, fetch_me

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
        Option(
            "--max-overflow-notify|-m",
            Args["max_overflow_notify", int],
            help_text="设置最大溢出通知次数 (默认3次, 0为禁用)",
        ),
        Option(
            "--target-droplets|-t",
            Args["target_droplets?#目标droplets值", int],
            help_text="设置目标droplets值,查询时显示达成时间(不附带参数则取消设置)",
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
matcher.shortcut("wpg", {"command": "wplace query $group"})


async def finish(msg: str) -> NoReturn:
    await UniMessage.text(msg).finish(reply_to=True)


async def prompt(msg: str) -> str:
    resp = await matcher.prompt(msg + "\n(回复 “取消” 以取消操作)")
    if resp is None:
        await finish("操作已取消")
    text = resp.extract_plain_text().strip()
    if text == "取消":
        await finish("操作已取消")
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
    except RequestFailed as e:
        await finish(f"验证失败: {e.msg}")
    except Exception:
        await finish("验证时发生意外错误，请稍后再试")

    cfg.save()
    await finish(f"添加成功\n{resp.format_notification()}")


async def _query_target_cfgs(
    event: Event,
    uni_target: MsgTarget,
    target: At | Literal["$group"] | None = None,
) -> list[ConfigModel]:
    if target == "$group" and uni_target.private:
        await finish("请在群聊中使用 $group 参数")

    if target == "$group":
        cfgs = [cfg for cfg in config.load() if cfg.target.verify(uni_target)]
        if not cfgs:
            await finish("群内没有用户绑定推送")
        return cfgs

    user_id = event.get_user_id() if target is None else target.target
    cfgs = [cfg for cfg in config.load() if cfg.user_id == user_id]
    if not cfgs:
        await finish("用户没有绑定任何账号")
    return cfgs


QueryConfigs = Annotated[list[ConfigModel], Depends(_query_target_cfgs)]


@matcher.assign("~query")
async def assign_query(cfgs: QueryConfigs) -> None:
    async def _fetch(config: ConfigModel) -> None:
        try:
            resp = await fetch_me(config)
            output.append(resp.format_notification(config.target_droplets))
        except RequestFailed as e:
            output.append(f"查询失败: {e.msg}")
        except Exception as e:
            output.append(f"查询时发生意外错误: {e!r}")

    output = ["查询结果:"]
    async with anyio.create_task_group() as tg:
        for cfg in cfgs:
            tg.start_soon(_fetch, cfg)

    await finish("\n\n".join(output))


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
        await finish("未找到对应的绑定账号")
    return cfgs[0]


SelectedConfig = Annotated[ConfigModel, Depends(_select_cfg)]


@matcher.assign("~config.notify-mins")
async def assign_config_notify_mins(
    cfg: SelectedConfig,
    notify_mins: int,
) -> None:
    cfg.notify_mins = notify_mins
    cfg.save()
    await finish(f"将在距离像素回满小于 {notify_mins} 分钟时推送通知")


@matcher.assign("~config.set-target")
async def assign_config_set_target(
    cfg: SelectedConfig,
    target: MsgTarget,
) -> None:
    cfg.target_data = target.dump()
    cfg.save()
    await finish("已设置当前会话为推送目标")


@matcher.assign("~config.max-overflow-notify")
async def assign_config_max_overflow_notify(
    cfg: SelectedConfig,
    max_overflow_notify: int,
) -> None:
    cfg.max_overflow_notify = max(0, max_overflow_notify)
    cfg.save()

    await finish(
        "已禁用溢出通知"
        if max_overflow_notify == 0
        else f"已设置最大溢出通知次数为 {max_overflow_notify} 次"
    )


@matcher.assign("~config.target-droplets")
async def assign_config_target_droplets(
    cfg: SelectedConfig,
    target_droplets: int | None,
) -> None:
    if target_droplets is not None and target_droplets < 0:
        await finish("目标 droplets 值必须为非负整数")

    cfg.target_droplets = target_droplets
    cfg.save()

    await finish(
        "已取消目标 droplets 设置"
        if target_droplets is None
        else f"已设置目标 droplets 值为 {target_droplets}💧"
    )


@matcher.assign("~remove")
async def assign_remove(cfg: SelectedConfig) -> None:
    config.remove(lambda c: c is cfg)
    await finish(f"移除成功: {cfg.wp_user_name}(ID: {cfg.wp_user_id})")
