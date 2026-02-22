from typing import Literal, NoReturn

from nonebot import logger
from nonebot.exception import MatcherException
from nonebot_plugin_alconna import UniMessage

from ..config import ranks
from ..fetch import RequestFailed, flatten_request_failed_msg
from ..rank import RANK_TITLE, find_regions_in_rect, get_regions_rank, render_rank
from ..schemas import RankType
from ..utils import WplacePixelCoords
from .depends import SceneID, SceneTemplate
from .matcher import finish, matcher, prompt


@matcher.assign("~rank.bind.revoke")
async def assign_rank_bind_revoke(sid: SceneID) -> None:
    if sid not in ranks.load():
        await finish("当前会话没有绑定任何 region ID")

    cfg = ranks.load()
    del cfg[sid]
    ranks.save(cfg)
    await finish("已取消当前会话的 region ID 绑定")


async def _bind_regions(
    sid: int,
    coord1: WplacePixelCoords,
    coord2: WplacePixelCoords,
) -> NoReturn:
    try:
        regions = await find_regions_in_rect(coord1, coord2)
    except* RequestFailed as e:
        logger.exception("查询区域内的 region ID 失败")
        await finish(f"查询区域内的 region ID 失败:\n{flatten_request_failed_msg(e)}")
    except* Exception as e:
        logger.exception("查询区域内的 region ID 时发生错误")
        await finish(f"查询区域内的 region ID 时发生意外错误: {e!r}")

    if not regions:
        await finish("未找到任何 region ID")

    cfg = ranks.load()
    cfg[sid] = set(regions.keys())
    ranks.save(cfg)
    await finish(
        f"成功绑定 {len(regions)} 个 region ID 到当前会话\n"
        f"{'\n'.join(f'{r.id}: {r.name} #{r.number}' for r in regions.values())}"
    )


@matcher.assign("~rank.bind.template")
async def assign_rank_bind_template(sid: SceneID, template: SceneTemplate) -> None:
    _, (coord1, coord2) = template.load()
    await _bind_regions(sid, coord1, coord2)


@matcher.assign("~rank.bind")
async def assign_rank_bind(sid: SceneID) -> None:
    coord1 = await prompt(
        "请发送对角坐标1(选点并复制BlueMarble的坐标)\n"
        "格式如: (Tl X: 123, Tl Y: 456, Px X: 789, Px Y: 012)"
    )
    coord2 = await prompt(
        "请发送对角坐标2(选点并复制BlueMarble的坐标)\n"
        "格式如: (Tl X: 123, Tl Y: 456, Px X: 789, Px Y: 012)"
    )

    try:
        c1 = WplacePixelCoords.parse(coord1)
        c2 = WplacePixelCoords.parse(coord2)
    except ValueError as e:
        await finish(f"坐标解析失败: {e}")

    await _bind_regions(sid, c1, c2)


RT_MAP: dict[Literal["today", "week", "month", "all"], RankType] = {
    "today": "today",
    "week": "week",
    "month": "month",
    "all": "all-time",
}


@matcher.assign("~rank.query")
async def assign_rank_query(
    sid: SceneID,
    rank_type: Literal["today", "week", "month", "all"],
) -> None:
    cfg = ranks.load()
    if sid not in cfg or not cfg[sid]:
        await finish("当前会话没有绑定任何 region ID，请先使用 wplace rank bind 绑定")

    rt = RT_MAP[rank_type]

    try:
        rank_data = await get_regions_rank(cfg[sid], rt)
    except* RequestFailed as e:
        logger.exception("获取排行榜失败")
        await finish(f"获取排行榜失败:\n{flatten_request_failed_msg(e)}")
    except* Exception as e:
        logger.exception("获取排行榜时发生错误")
        await finish(f"获取排行榜时发生意外错误: {e!r}")

    if not rank_data:
        await finish("未获取到任何排行榜数据，可能是 region ID 无效或暂无数据")

    try:
        img = await render_rank(rt, rank_data)
        await finish(UniMessage.image(raw=img))
    except MatcherException:
        raise
    except Exception:
        logger.exception("渲染排行榜时发生错误")

    # fallback
    msg = "\n".join(
        f"{idx}. {r.name} #{r.user_id} - {r.pixels} 像素"
        for idx, r in enumerate(rank_data, 1)
    )
    await finish(f"{RANK_TITLE[rt]}:\n{msg}")
