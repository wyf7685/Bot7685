from typing import Annotated, Literal, NoReturn

import anyio
from nonebot import logger
from nonebot.adapters import Event
from nonebot.exception import MatcherException
from nonebot.params import Depends
from nonebot_plugin_alconna import (
    Alconna,
    Args,
    At,
    CommandMeta,
    MsgTarget,
    Option,
    Query,
    Subcommand,
    UniMessage,
    on_alconna,
)

from src.utils import ParamOrPrompt

from .config import UserConfig, ranks, users
from .fetch import RankType, RequestFailed, fetch_me
from .preview import download_preview
from .rank import RANK_TITLE, find_regions_in_rect, get_regions_rank, render_rank
from .scheduler import FETCH_INTERVAL_MINS
from .utils import parse_coords

alc = Alconna(
    "wplace",
    Subcommand(
        "add",
        Args["token?#WPlace Cookies 中的 j (token)", str],
        Args["cf_clearance?#WPlace Cookies 中的 cf_clearance", str],
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
        Args["identifier?#账号标识,ID或用户名", str],
        Option(
            "--notify-mins|-n",
            Args["notify_mins", int],
            help_text=f"提前多少分钟通知 (默认10,最小{FETCH_INTERVAL_MINS})",
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
        Args["identifier?#账号标识,ID或用户名", str],
        alias={"rm"},
        help_text="移除已绑定的账号",
    ),
    Subcommand(
        "bind",
        Args["identifier?#账号标识,ID或用户名", str],
        help_text="将账号绑定到当前群组(使其对$group可见)",
    ),
    Subcommand(
        "preview",
        Args["coord1?#坐标1", str]["coord2?#坐标2", str],
        Option("--background|-b", Args["background#背景色RGB", str]),
        help_text="获取指定区域的预览图",
    ),
    Subcommand(
        "rank",
        Subcommand(
            "bind",
            Option("--revoke|-r"),
            Args["coord1?#坐标1", str]["coord2?#坐标2", str],
        ),
        Subcommand(
            "today",
            Option("--all-users|-a"),
            help_text="查询指定区域的当日排行榜",
        ),
        Subcommand(
            "week",
            Option("--all-users|-a"),
            help_text="查询指定区域的本周排行榜",
        ),
        Subcommand(
            "month",
            Option("--all-users|-a"),
            help_text="查询指定区域的本月排行榜",
        ),
        Subcommand(
            "all",
            Option("--all-users|-a"),
            help_text="查询指定区域的历史总排行榜",
        ),
        help_text="查询指定区域的排行榜",
    ),
    meta=CommandMeta(
        description="WPlace 查询",
        usage="wplace <add|query|config|remove> [参数...]",
        author="wyf7685",
    ),
)
matcher = on_alconna(alc, aliases={"wp"})
matcher.shortcut("wpq", {"command": "wplace query {*}"})
matcher.shortcut("wpg", {"command": "wplace query $group"})


async def finish(msg: str | UniMessage) -> NoReturn:
    await (UniMessage.text(msg) if isinstance(msg, str) else msg).finish(reply_to=True)


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
    token: str = ParamOrPrompt(
        "token",
        lambda: prompt("请输入 WPlace Cookies 中的 j (token)"),
    ),
    cf_clearance: str = ParamOrPrompt(
        "cf_clearance",
        lambda: prompt("请输入 WPlace Cookies 中的 cf_clearance"),
    ),
) -> None:
    cfg = UserConfig(
        token=token,
        cf_clearance=cf_clearance,
        target_data=target.dump(),
        user_id=event.get_user_id(),
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
        f"{i}. {cfg.wp_user_name}(ID: {cfg.wp_user_id})\n"
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


SelectedConfig = Annotated[UserConfig, Depends(_select_cfg)]


@matcher.assign("~config.notify-mins")
async def assign_config_notify_mins(
    cfg: SelectedConfig,
    notify_mins: int,
) -> None:
    cfg.notify_mins = max(FETCH_INTERVAL_MINS, notify_mins)
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
async def assign_remove(cfg: SelectedConfig) -> None:
    users.remove(lambda c: c is cfg)
    await finish(f"移除成功: {cfg.wp_user_name}(ID: {cfg.wp_user_id})")


@matcher.assign("~bind")
async def assign_bind(
    cfg: SelectedConfig,
    target: MsgTarget,
) -> None:
    if target.private:
        await finish("请在群聊中使用绑定功能")

    cfg.bind_groups.add(target.id)
    cfg.save()
    await finish(f"{cfg.wp_user_name}(ID: {cfg.wp_user_id}) 已绑定到当前群组")


@matcher.assign("~preview")
async def assign_preview(
    coord1: str = ParamOrPrompt(
        "coord1",
        lambda: prompt("请输入第一个坐标(选点并复制BlueMarble的坐标)"),
    ),
    coord2: str = ParamOrPrompt(
        "coord2",
        lambda: prompt("请输入第二个坐标(选点并复制BlueMarble的坐标)"),
    ),
    background: str | None = None,
) -> None:
    try:
        c1 = parse_coords(coord1)
        c2 = parse_coords(coord2)
    except ValueError as e:
        await finish(f"坐标解析失败: {e}")

    try:
        img_bytes = await download_preview(c1, c2, background)
    except Exception as e:
        await finish(f"获取预览图失败: {e!r}")

    await finish(UniMessage.image(raw=img_bytes))


@matcher.assign("~rank.bind.revoke")
async def assign_rank_bind_revoke(target: MsgTarget) -> None:
    if target.id not in ranks.load():
        await finish("当前群组没有绑定任何 region ID")

    cfg = ranks.load()
    del cfg[target.id]
    ranks.save(cfg)
    await finish("已取消当前群组的 region ID 绑定")


@matcher.assign("~rank.bind")
async def assign_rank_bind(
    target: MsgTarget,
    coord1: str = ParamOrPrompt(
        "coord1",
        lambda: prompt("请输入第一个坐标(选点并复制BlueMarble的坐标)"),
    ),
    coord2: str = ParamOrPrompt(
        "coord2",
        lambda: prompt("请输入第二个坐标(选点并复制BlueMarble的坐标)"),
    ),
) -> None:
    try:
        c1 = parse_coords(coord1)
        c2 = parse_coords(coord2)
    except ValueError as e:
        await finish(f"坐标解析失败: {e}")

    try:
        regions = await find_regions_in_rect(c1, c2)
    except RequestFailed as e:
        await finish(f"查询区域内的 region ID 失败: {e.msg}")
    except Exception as e:
        await finish(f"查询区域内的 region ID 时发生意外错误: {e!r}")

    if not regions:
        await finish("未找到任何 region ID")

    cfg = ranks.load()
    cfg[target.id] = set(regions.keys())
    ranks.save(cfg)
    await finish(
        f"成功绑定 {len(regions)} 个 region ID 到当前群组\n"
        f"{'\n'.join(f'{r.id}: {r.name} #{r.number}' for r in regions.values())}"
    )


async def _handle_rank_query(
    target: MsgTarget,
    rank_type: RankType,
    only_known_users: bool = True,  # noqa
) -> None:
    if target.private:
        await finish("请在群聊中使用排行榜查询功能")

    cfg = ranks.load()
    if target.id not in cfg or not cfg[target.id]:
        await finish("当前群组没有绑定任何 region ID，请先使用 wplace rank bind 绑定")

    try:
        rank_data = await get_regions_rank(cfg[target.id], rank_type)
    except RequestFailed as e:
        await finish(f"获取排行榜失败: {e.msg}")
    except Exception as e:
        await finish(f"获取排行榜时发生意外错误: {e!r}")

    if only_known_users:
        known_users = {*filter(None, (cfg.wp_user_id for cfg in users.load()))}
        rank_data = [entry for entry in rank_data if entry[0] in known_users]

    if not rank_data:
        await finish("未获取到任何排行榜数据，可能是 region ID 无效或暂无数据")

    try:
        img = await render_rank(rank_type, rank_data)
        await finish(UniMessage.image(raw=img))
    except MatcherException:
        raise
    except Exception:
        logger.opt(exception=True).warning("渲染排行榜时发生错误")

    # fallback
    msg = "\n".join(
        f"{idx}. {user_name} (ID: {user_id}) - {painted} 像素"
        for idx, (user_id, user_name, painted) in enumerate(rank_data, 1)
    )
    await finish(f"{RANK_TITLE[rank_type]}:\n{msg}")


def _rank_query(rank_type: RankType) -> None:
    path = rank_type.split("-")[0]

    async def assign_rank(
        target: MsgTarget,
        all_users: Query[bool] = Query(f"~rank.{path}.all-users", default=False),  # noqa: B008
    ) -> None:
        await _handle_rank_query(target, rank_type, not all_users.result)

    assign_rank.__name__ += f"_{path}"
    matcher.assign(f"~rank.{path}")(assign_rank)


[_rank_query(rt) for rt in ("today", "week", "month", "all-time")]
