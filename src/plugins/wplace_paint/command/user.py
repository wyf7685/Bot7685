import contextlib
from typing import Literal

import anyio
from nonebot import logger
from nonebot.adapters import Bot, Event
from nonebot_plugin_alconna import CustomNode, MsgTarget, SupportScope, UniMessage

from ..config import UserConfig, users
from ..fetch import RequestFailed, fetch_me, flatten_request_failed_msg
from ..scheduler import FETCH_INTERVAL_MINS, expire_push_cache
from ..schemas import PurchaseItem
from ..utils import normalize_color_name, parse_token
from .depends import QueryConfigs, SelectedUserConfig, TargetHash, TargetTemplate
from .matcher import finish, matcher


@matcher.assign("~bind")
async def assign_bind(
    bot: Bot,
    event: Event,
    target: MsgTarget,
    token: str,
    cf_clearance: str,
) -> None:
    if not (payload := parse_token(token)) or payload.is_expired():
        await finish("无效的 token")

    cfg = UserConfig(
        token=token,
        cf_clearance=cf_clearance,
        target_data=target.dump(),
        user_id=event.get_user_id(),
        adapter=bot.type,
        wp_user_id=payload.userId,
    )

    try:
        resp = await fetch_me(cfg)
    except* RequestFailed as e:
        logger.exception("验证 WPlace 账号时发生错误")
        await finish(f"验证失败:\n{flatten_request_failed_msg(e)}")
    except* Exception as e:
        logger.exception("验证 WPlace 账号时发生意外错误")
        await finish(f"验证时发生意外错误: {e!r}")

    cfg.save()
    await expire_push_cache(cfg)
    await finish(f"添加成功\n{resp.format_notification()}")


@matcher.assign("~query")
async def assign_query(
    event: Event,
    target: MsgTarget,
    cfgs: QueryConfigs,
) -> None:
    async def _fetch(cfg: UserConfig) -> None:
        try:
            resp = await fetch_me(cfg)
            result = resp.format_notification(cfg.target_droplets)
        except* RequestFailed as e:
            logger.exception(
                f"查询 WPlace 账号 {cfg.wp_user_name} #{cfg.wp_user_id} 时发生错误"
            )
            result = f"查询失败:\n{flatten_request_failed_msg(e)}"
        except* Exception as e:
            logger.exception(
                f"查询 WPlace 账号 {cfg.wp_user_name} #{cfg.wp_user_id} 时发生意外错误"
            )
            result = f"查询时发生意外错误:\n{e!r}"

        output[cfg.wp_user_id] = cfg.user_id, result

    output: dict[int, tuple[str, str]] = {}
    async with anyio.create_task_group() as tg:
        for cfg in cfgs:
            tg.start_soon(_fetch, cfg)

    results = [r for _, (_, r) in sorted(output.items(), key=lambda x: (x[1][0], x[0]))]

    if target.private or len(results) == 1 or target.scope != SupportScope.qq_client:
        await finish("查询结果:\n\n" + "\n\n".join(results))

    nodes = [
        CustomNode(event.get_user_id(), f"查询结果 - {idx}", content, context=target.id)
        for idx, content in enumerate(results, start=1)
    ]
    await UniMessage.reference(*nodes).finish(reply_to=True)


@matcher.assign("~config.notify-mins")
async def assign_config_notify_mins(
    cfg: SelectedUserConfig,
    notify_mins: int,
) -> None:
    cfg.notify_mins = max(FETCH_INTERVAL_MINS, notify_mins)
    cfg.save()
    await finish(f"将在距离像素回满小于 {notify_mins} 分钟时推送通知")


@matcher.assign("~config.bind-target")
async def assign_config_bind_target(
    cfg: SelectedUserConfig,
    target: MsgTarget,
    target_hash: TargetHash,
) -> None:
    if target.private:
        await finish("请在群聊中使用绑定功能")

    cfg.bind_groups.add(target_hash)
    cfg.save()
    await finish(f"{cfg.wp_user_name} #{cfg.wp_user_id} 已绑定到当前群组")


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


@matcher.assign("~config.auto-paint")
async def assign_config_auto_paint(
    cfg: SelectedUserConfig,
    _: TargetTemplate,
    target_hash: TargetHash,
) -> None:
    if cfg.auto_paint_target_hash == target_hash:
        cfg.auto_paint_target_hash = None
        msg = "已禁用自动绘制功能"
    else:
        cfg.auto_paint_target_hash = target_hash
        msg = "已启用自动绘制功能，将使用当前会话模板进行绘制"
    cfg.save()
    await finish(msg)


@matcher.assign("~config.auto-purchase")
async def assign_config_auto_purchase(
    cfg: SelectedUserConfig,
    item_id: int | Literal["list"] | None = None,
) -> None:
    if item_id == "list":
        await finish(
            "可自动购买的物品列表:\n"
            + "\n".join(
                f"{item.value} - {item.item_name}: {item.price}"
                for item in PurchaseItem
            )
            + "\n\n使用命令时请提供物品ID,或使用 'list' 查看此列表"
        )

    if item_id is None:
        cfg.auto_purchase = None
        msg = "已取消自动购买物品设置"
    else:
        try:
            cfg.auto_purchase = PurchaseItem(item_id)
        except ValueError:
            await finish(f"无效的物品ID: {item_id}")
        msg = (
            "已设置自动购买物品为 "
            f"{cfg.auto_purchase.item_name} (ID: {cfg.auto_purchase.value})"
        )

    cfg.save()
    await finish(msg)


@matcher.assign("~remove")
async def assign_remove(cfg: SelectedUserConfig) -> None:
    users.remove(lambda c: c is cfg)
    await finish(f"移除成功: {cfg.wp_user_name} #{cfg.wp_user_id}")


@matcher.assign("~find-color")
async def assign_find_color(
    target: MsgTarget,
    target_hash: TargetHash,
    color_name: str,
) -> None:
    if target.private:
        await finish("请在群聊中使用查询颜色功能")

    if not (fixed_name := normalize_color_name(color_name)):
        await finish(f"无效的颜色名称: {color_name}")

    async def check_user(cfg: UserConfig) -> None:
        with contextlib.suppress(Exception):
            resp = await fetch_me(cfg)
            if fixed_name in resp.own_colors:
                result.append(f"- {cfg.wp_user_name} #{cfg.wp_user_id}")

    result: list[str] = []
    async with anyio.create_task_group() as tg:
        for cfg in users.load():
            if cfg.target.verify(target) or target_hash in cfg.bind_groups:
                tg.start_soon(check_user, cfg)

    await finish(
        f"拥有 {fixed_name} 颜色的用户:\n" + "\n".join(result)
        if result
        else f"群内没有用户拥有颜色 {fixed_name}"
    )
