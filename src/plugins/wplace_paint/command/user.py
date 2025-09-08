from typing import Annotated, Literal

import anyio
from nonebot.adapters import Bot, Event
from nonebot.params import Depends
from nonebot_plugin_alconna import At, MsgTarget

from ..config import UserConfig, users
from ..fetch import RequestFailed, fetch_me
from ..scheduler import FETCH_INTERVAL_MINS
from .matcher import finish, matcher, prompt


@matcher.assign("~add")
async def assign_add(
    bot: Bot,
    event: Event,
    target: MsgTarget,
    token: str,
    cf_clearance: str,
) -> None:
    cfg = UserConfig(
        token=token,
        cf_clearance=cf_clearance,
        target_data=target.dump(),
        user_id=event.get_user_id(),
        adapter=bot.type,
    )

    try:
        resp = await fetch_me(cfg)
    except RequestFailed as e:
        await finish(f"验证失败: {e.msg}")
    except Exception as e:
        await finish(f"验证时发生意外错误: {e!r}")

    cfg.save()
    await finish(f"添加成功\n{resp.format_notification()}")


async def _query_target_cfgs(
    event: Event,
    uni_target: MsgTarget,
    target: At | Literal["$group"] | None = None,
) -> list[UserConfig]:
    if target == "$group" and uni_target.private:
        await finish("请在群聊中使用 $group 参数")

    if target == "$group":
        cfgs = [
            cfg
            for cfg in users.load()
            if cfg.target.verify(uni_target) or uni_target.id in cfg.bind_groups
        ]
        if not cfgs:
            await finish("群内没有用户绑定账号")
        return cfgs

    user_id = event.get_user_id() if target is None else target.target
    cfgs = [cfg for cfg in users.load() if cfg.user_id == user_id]
    if not cfgs:
        await finish("用户没有绑定任何账号")
    return cfgs


QueryConfigs = Annotated[list[UserConfig], Depends(_query_target_cfgs)]


@matcher.assign("~query")
async def assign_query(cfgs: QueryConfigs) -> None:
    async def _fetch(config: UserConfig) -> None:
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


async def _select_cfg(
    event: Event,
    identifier: str | None = None,
) -> UserConfig:
    user_id = event.get_user_id()
    user_cfgs = [cfg for cfg in users.load() if cfg.user_id == user_id]
    if not user_cfgs:
        await finish("你还没有绑定任何账号")

    if identifier is not None:
        gen = (
            cfg
            for cfg in filter(lambda c: c.wp_user_id is not None, user_cfgs)
            if str(cfg.wp_user_id) == identifier or cfg.wp_user_name == identifier
        )
        if cfg := next(gen, None):
            return cfg
        await finish("未找到对应的绑定账号")

    if len(user_cfgs) == 1:
        return user_cfgs[0]

    formatted_cfgs = "".join(
        f"{i}. {cfg.wp_user_name} #{cfg.wp_user_id}\n"
        for i, cfg in enumerate(user_cfgs, start=1)
    )
    msg = "你绑定了多个账号，请回复要操作的账号序号:\n" + formatted_cfgs

    while True:
        text = await prompt(msg)
        if text.isdigit():
            idx = int(text)
            if 1 <= idx <= len(user_cfgs):
                return user_cfgs[idx - 1]
        msg = "无效的序号，请重新输入:\n" + formatted_cfgs


SelectedUserConfig = Annotated[UserConfig, Depends(_select_cfg)]


@matcher.assign("~config.notify-mins")
async def assign_config_notify_mins(
    cfg: SelectedUserConfig,
    notify_mins: int,
) -> None:
    cfg.notify_mins = max(FETCH_INTERVAL_MINS, notify_mins)
    cfg.save()
    await finish(f"将在距离像素回满小于 {notify_mins} 分钟时推送通知")


@matcher.assign("~config.set-target")
async def assign_config_set_target(
    cfg: SelectedUserConfig,
    target: MsgTarget,
) -> None:
    cfg.target_data = target.dump()
    cfg.save()
    await finish("已设置当前会话为推送目标")


@matcher.assign("~config.max-overflow-notify")
async def assign_config_max_overflow_notify(
    cfg: SelectedUserConfig,
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
    cfg: SelectedUserConfig,
    target_droplets: int | None = None,
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
async def assign_remove(cfg: SelectedUserConfig) -> None:
    users.remove(lambda c: c is cfg)
    await finish(f"移除成功: {cfg.wp_user_name} #{cfg.wp_user_id}")


@matcher.assign("~bind")
async def assign_bind(
    cfg: SelectedUserConfig,
    target: MsgTarget,
) -> None:
    if target.private:
        await finish("请在群聊中使用绑定功能")

    cfg.bind_groups.add(target.id)
    cfg.save()
    await finish(f"{cfg.wp_user_name} #{cfg.wp_user_id} 已绑定到当前群组")
