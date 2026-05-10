"""定时分析调度 — 基于订阅文件，支持传统+增量双模式。"""

import time as time_mod

from apscheduler.triggers.cron import CronTrigger
from nonebot.log import logger
from nonebot_plugin_alconna import Target, UniMessage
from nonebot_plugin_apscheduler import scheduler
from nonebot_plugin_uninfo.params import get_interface

from ..config import config
from ..persistence.incremental_store import IncrementalStore
from ..persistence.subscription import subscriptions
from ..rendering import render_image
from ..services.analysis_service import (
    AnalysisResult,
    run_daily_analysis,
    run_incremental_analysis,
    run_incremental_final_report,
)

_incremental_store = IncrementalStore()


def setup_scheduled_jobs() -> None:
    """注册定时分析任务（在 on_startup 中调用）。"""
    if not config.auto_analysis.enabled:
        return

    # 注册报告时间点任务（传统 + 增量最终报告）
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

    # 如果启用了增量模式，注册增量分析任务
    if config.incremental.enabled:
        _register_incremental_jobs()


def _register_incremental_jobs() -> None:
    """在活跃时段内注册增量分析定时任务。"""
    incr = config.incremental
    active_start = incr.active_start_hour
    active_end = incr.active_end_hour
    interval = incr.interval_minutes
    max_daily = incr.max_daily_analyses

    trigger_times: list[tuple[int, int]] = []
    current_minutes = active_start * 60
    end_minutes = active_end * 60

    while current_minutes < end_minutes and len(trigger_times) < max_daily:
        hour = current_minutes // 60
        minute = current_minutes % 60
        trigger_times.append((hour, minute))
        current_minutes += interval

    for hour, minute in trigger_times:
        job_id = f"group_daily_incremental_{hour:02d}{minute:02d}"
        scheduler.add_job(
            _incremental_analysis_job,
            trigger=CronTrigger(hour=hour, minute=minute),
            id=job_id,
            misfire_grace_time=60,
            replace_existing=True,
        )
        logger.opt(colors=True).info(f"已注册增量分析: <y>{hour:02d}:{minute:02d}</>")


async def _auto_analysis_job() -> None:
    """定时分析任务 — 遍历所有订阅执行分析（支持传统+增量双模式）。"""
    subs = subscriptions.load()
    if not subs:
        return

    incremental_enabled = config.incremental.enabled

    for sub in subs:
        try:
            target = sub.target
            session = sub.session_data
            bot = await target.select()

            # 判断模式：订阅级别增量开关 + 全局增量开关
            use_incremental = incremental_enabled and sub.incremental_enabled

            if use_incremental:
                result = await run_incremental_final_report(
                    session, days=sub.analysis_days
                )
                if result is None:
                    logger.warning(
                        f"增量报告: {session.scene.name or session.scene.id} 无批次数据"
                    )
                    continue

                await _send_report(result, target)

                # 清理过期批次
                try:
                    before_ts = time_mod.time() - (sub.analysis_days * 2 * 24 * 3600)
                    group_id = session.scene.id
                    await _incremental_store.cleanup_old_batches(group_id, before_ts)
                except Exception as cleanup_err:
                    logger.warning(f"过期批次清理失败: {cleanup_err}")

                logger.opt(colors=True).info(
                    f"增量报告完成: <g>{session.scene.name or session.scene.id}</>"
                )
            else:
                result = await run_daily_analysis(
                    bot,
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


async def _incremental_analysis_job() -> None:
    """增量分析任务 — 遍历所有增量模式订阅执行小批量分析。"""
    subs = subscriptions.load()
    if not subs:
        return

    for sub in subs:
        if not sub.incremental_enabled:
            continue

        try:
            session = sub.session_data
            bot = await sub.target.select()

            await run_incremental_analysis(
                bot,
                session,
                days=sub.analysis_days,
            )
        except Exception as e:
            logger.opt(colors=True).error(
                f"增量分析失败 ({sub.session_data.scene.id}): {e}"
            )


async def _send_report(result: AnalysisResult, target: Target) -> None:
    """根据配置发送报告，图片失败时降级为文本。"""
    if config.output_format == "image" and (
        interface := get_interface(await target.select())
    ):
        image_bytes = await render_image(result, interface)
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
