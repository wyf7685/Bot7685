"""定时分析调度 — 基于订阅文件。"""

from apscheduler.triggers.cron import CronTrigger
from nonebot.log import logger
from nonebot_plugin_alconna import Target, UniMessage
from nonebot_plugin_apscheduler import scheduler
from nonebot_plugin_uninfo.params import get_interface

from ..config import config
from ..persistence.subscription import subscriptions
from ..rendering.generator import render_image
from ..services.analysis_service import AnalysisResult, run_daily_analysis


def setup_scheduled_jobs() -> None:
    """注册定时分析任务（在 on_startup 中调用）。"""
    if not config.auto_analysis.enabled:
        return

    for time_str in config.auto_analysis.times:
        parts = time_str.split(":")
        if len(parts) != 2:
            logger.warning(f"无效的定时分析时间格式: {time_str}")
            continue

        hour, minute = int(parts[0]), int(parts[1])
        job_id = f"group_daily_analysis_{hour:02d}{minute:02d}"

        existing = scheduler.get_job(job_id)
        if existing:
            existing.remove()

        scheduler.add_job(
            _auto_analysis_job,
            trigger=CronTrigger(hour=hour, minute=minute),
            id=job_id,
            misfire_grace_time=60,
            replace_existing=True,
        )
        logger.opt(colors=True).info(f"已注册定时群分析: <y>{hour:02d}:{minute:02d}</>")


async def _auto_analysis_job() -> None:
    """定时分析任务 — 遍历所有订阅执行分析。"""
    subs = subscriptions.load()
    if not subs:
        return

    for sub in subs:
        try:
            target = sub.target
            session = sub.session_data

            result = await run_daily_analysis(
                session,
                days=sub.analysis_days,
            )
            if result is None:
                logger.warning(
                    f"定时分析: {session.scene.name or session.scene.id} 消息不足"
                )
                continue

            await _send_report(result, target)
            logger.opt(colors=True).info(
                f"定时分析完成: <g>{session.scene.name or session.scene.id}</>"
            )
        except Exception as e:
            logger.opt(colors=True).error(
                f"定时分析失败 ({sub.session_data.scene.id}): {e}"
            )


async def _send_report(result: AnalysisResult, target: Target) -> None:
    """根据配置发送报告，图片失败时降级为文本。"""
    if config.output_format == "image":
        try:
            bot = await target.select()
            iface = get_interface(bot)
        except Exception:
            iface = None

        avatar_getter = None
        if iface:

            async def _get(uid: str) -> str | None:
                user = await iface.get_user(uid)
                return user.avatar if user else None

            avatar_getter = _get

        image_bytes = await render_image(result, avatar_getter=avatar_getter)
        if image_bytes:
            await UniMessage.image(raw=image_bytes).send(target)
            return
    await UniMessage.text(_format_text_report(result)).send(target)


def _format_text_report(result: AnalysisResult) -> str:
    """生成纯文本报告。"""
    lines = [
        f"📊 {result.group_name} 群聊日报",
        f"消息: {result.statistics.message_count} | "
        f"参与者: {result.statistics.participant_count}",
    ]

    if result.topics:
        lines.append("\n📌 话题:")
        for i, t in enumerate(result.topics[:5], 1):
            lines.append(f"  {i}. {t.topic} - {t.detail[:50]}")

    if result.golden_quotes:
        lines.append("\n💬 金句:")
        lines.extend(f"  「{q.content[:30]}」" for q in result.golden_quotes[:3])

    return "\n".join(lines)
