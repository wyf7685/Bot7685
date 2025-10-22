import random
import uuid

import httpx
from nonebot import logger
from nonebot.adapters import Bot, Event
from nonebot.exception import MatcherException
from nonebot.utils import flatten_exception_group
from nonebot_plugin_alconna import File, Image, UniMessage, image_fetch
from nonebot_plugin_waiter import waiter

from src.plugins.group_pipe import get_converter

from ..config import IMAGE_DIR, TemplateConfig, templates
from ..fetch import RequestFailed, flatten_request_failed_msg
from ..preview import download_preview
from ..template import (
    calc_template_diff,
    download_template_preview,
    format_post_paint_result,
    get_color_location,
    post_paint,
    render_progress,
    render_template_with_color,
)
from ..utils import WplacePixelCoords, normalize_color_name, parse_color_names
from .depends import TargetHash, TargetTemplate
from .matcher import finish, matcher, prompt
from .user import SelectedUserConfig


@matcher.assign("~preview")
async def assign_preview(
    coord1: str,
    coord2: str,
    background: str | None = None,
) -> None:
    try:
        c1 = WplacePixelCoords.parse(coord1)
        c2 = WplacePixelCoords.parse(coord2)
    except ValueError as e:
        await finish(f"坐标解析失败: {e}")

    try:
        img_bytes = await download_preview(c1, c2, background)
    except Exception as e:
        await finish(f"获取预览图失败: {e!r}")

    await finish(UniMessage.image(raw=img_bytes))


@matcher.assign("~template.bind.revoke")
async def assign_template_bind_revoke(key: TargetHash) -> None:
    cfgs = templates.load()
    if key not in cfgs:
        await finish("当前会话没有绑定模板")

    try:
        cfgs[key].file.unlink(missing_ok=True)
    except Exception:
        logger.opt(exception=True).warning("删除模板图片时发生错误")

    del cfgs[key]
    templates.save(cfgs)
    await finish("已取消当前会话的模板绑定")


async def extract_image(bot: Bot, event: Event) -> bytes | None:
    async def download_from_url(url: str) -> bytes:
        async with httpx.AsyncClient() as client:
            resp = await client.get(url)
            return resp.raise_for_status().content

    converter = get_converter(bot)
    msg = await converter.get_message(event)
    if msg is None:
        return None
    unimsg = await converter(bot).convert(msg)
    if segs := unimsg.include(Image, File):
        seg: Image | File = segs[0]
        if seg.raw is not None:
            return seg.raw_bytes
        if seg.url is not None:
            return await download_from_url(seg.url)
        if isinstance(seg, Image):
            return await image_fetch(event, bot, {}, seg)
    return None


async def prompt_image() -> bytes:
    await matcher.send("请发送模板图片\n(回复其他内容以取消操作)")

    @waiter(["message"], matcher, keep_session=True)
    async def wait(bot: Bot, event: Event) -> tuple[Bot, Event]:
        return bot, event

    res = await wait.wait(timeout=120)
    if res is None:
        await finish("操作已取消")
    img_bytes = await extract_image(*res)
    if img_bytes is None:
        await finish("获取图片数据失败")
    return img_bytes


@matcher.assign("~template.bind")
async def assign_template_bind(key: TargetHash) -> None:
    coord = await prompt(
        "请发送模板起始坐标(选点并复制BlueMarble的坐标)\n"
        "格式如: (Tl X: 123, Tl Y: 456, Px X: 789, Px Y: 012)"
    )

    try:
        coords = WplacePixelCoords.parse(coord)
    except ValueError as e:
        await finish(f"坐标解析失败: {e}")

    img_bytes = await prompt_image()
    fp = IMAGE_DIR / f"{uuid.uuid4()}.png"
    fp.write_bytes(img_bytes)

    cfgs = templates.load()
    if key in cfgs:
        try:
            cfgs[key].file.unlink(missing_ok=True)
        except Exception:
            logger.opt(exception=True).warning("删除旧模板图片时发生错误")

    cfgs[key] = TemplateConfig(coords=coords, image=fp.name)
    templates.save(cfgs)
    await finish(f"模板绑定成功\n{coords.human_repr()}")


@matcher.assign("~template.preview")
async def assign_template_preview(
    cfg: TargetTemplate,
    background: str | None = None,
    pixels: int = 0,
) -> None:
    if pixels < 0:
        await finish("边框像素不能为负数")

    try:
        img_bytes = await download_template_preview(cfg, background, pixels)
    except* httpx.HTTPError as exc_group:
        await finish(
            "获取模板预览失败:\n"
            + "\n".join(f"- {e!r}" for e in flatten_exception_group(exc_group))
        )
    except* Exception as exc_group:
        logger.opt(exception=True).warning("获取模板预览时发生错误")
        await finish(f"获取模板预览时发生意外错误: {exc_group!r}")

    await finish(UniMessage.image(raw=img_bytes))


@matcher.assign("~template.progress")
async def assign_template_progress(cfg: TargetTemplate) -> None:
    try:
        progress_data = await calc_template_diff(cfg)
    except* RequestFailed as e:
        await finish(f"获取模板进度失败:\n{flatten_request_failed_msg(e)}")
    except* Exception as e:
        await finish(f"计算模板进度时发生意外错误: {e!r}")

    if not progress_data:
        await finish("模板中没有任何需要绘制的像素")

    try:
        img_bytes = await render_progress(progress_data)
        await finish(UniMessage.image(raw=img_bytes))
    except MatcherException:
        raise
    except Exception:
        logger.opt(exception=True).warning("渲染模板进度时发生错误")

    # fallback
    drawn_pixels = sum(entry.drawn for entry in progress_data)
    total_pixels = sum(entry.total for entry in progress_data)
    remaining_pixels = total_pixels - drawn_pixels
    overall_progress = (drawn_pixels / total_pixels * 100) if total_pixels > 0 else 0
    msg_lines = [
        f"总体进度: {drawn_pixels} / {total_pixels} "
        f"({overall_progress:.2f}%)，"
        f"剩余 {remaining_pixels} 像素",
        "各颜色进度:",
    ]
    msg_lines.extend(
        f"{'★' if entry.is_paid else ''}{entry.name}: "
        f"{entry.drawn} / {entry.total} "
        f"({entry.progress:.2f}%)"
        for entry in progress_data
    )
    await finish("\n".join(msg_lines))


@matcher.assign("~template.color")
async def assign_template_color(
    cfg: TargetTemplate,
    color_name: list[str],
    background: str | None = None,
) -> None:
    fixed_colors = parse_color_names(color_name)
    if not fixed_colors:
        await finish(f"无效的颜色名称:\n{' '.join(color_name)}")

    try:
        img_bytes = await render_template_with_color(cfg, fixed_colors, background)
        await finish(
            UniMessage.text(
                "渲染模板图:\n" + "\n".join(f"- {name}" for name in fixed_colors)
            ).image(raw=img_bytes)
        )
    except* RequestFailed as e:
        await finish(f"获取模板图失败:\n{flatten_request_failed_msg(e)}")
    except* MatcherException:
        raise
    except* Exception as e:
        logger.opt(exception=True).warning("渲染模板图时发生错误")
        await finish(f"渲染模板图时发生意外错误: {e!r}")


@matcher.assign("~template.locate")
async def assign_template_locate(
    cfg: TargetTemplate,
    color_name: str,
    max_count: int = 5,
) -> None:
    if not (fixed_name := normalize_color_name(color_name)):
        await finish(f"无效的颜色名称: {color_name}")

    try:
        locations = await get_color_location(cfg, fixed_name)
    except RequestFailed as e:
        await finish(f"获取模板图失败: {e.msg}")
    except Exception as e:
        logger.opt(exception=True).warning("查询模板颜色位置时发生错误")
        await finish(f"查询模板颜色位置时发生意外错误: {e!r}")

    if not locations:
        await finish(f"模板中没有待绘制的 {fixed_name} 像素")

    base = cfg.coords
    urls: list[str] = []
    random.shuffle(locations)
    for x, y in locations[:max_count]:
        coord = base.offset(x, y)
        urls.append(f"[{coord.human_repr()}]\n{coord.to_share_url()}\n")

    msg = (
        f"模板中共有 {len(locations)} 个待绘制的 {fixed_name} 像素\n"
        f"以下是前 {len(urls)} 个像素的位置:\n\n"
    ) + "\n".join(urls)
    await finish(msg)


@matcher.assign("~template.paint")
async def assign_template_paint(
    tp: TargetTemplate,
    user: SelectedUserConfig,
    pawtect_token: str | None = None,
) -> None:
    try:
        painted, color_map = await post_paint(user, tp, pawtect_token)
    except* RequestFailed as e:
        await finish(f"绘制模板失败:\n{flatten_request_failed_msg(e)}")
    except* Exception as e:
        logger.opt(exception=True).warning("绘制模板时发生错误")
        await finish(f"绘制模板时发生意外错误: {e!r}")

    await finish(format_post_paint_result(painted, color_map))
