"""群分析命令 — 手动分析 + 订阅管理。"""

from typing import Annotated

from nonebot.adapters import Bot
from nonebot_plugin_alconna import (
    Alconna,
    Args,
    Arparma,
    CommandMeta,
    MsgTarget,
    Option,
    Subcommand,
    UniMessage,
    on_alconna,
)
from nonebot_plugin_alconna.builtins.extensions.telegram import TelegramSlashExtension
from nonebot_plugin_uninfo import Interface, QueryInterface, Uninfo

from src.plugins.trusted import TrustedUser

from ..config import config
from ..persistence.subscription import (
    AnalysisSubscription,
    add_subscription,
    list_subscriptions,
    remove_subscription,
    subscriptions,
)
from ..rendering import render_image
from ..services.analysis_service import AnalysisResult, run_daily_analysis

alc = Alconna(
    "group_analysis",
    Args["days?", int],
    Subcommand(
        "subscribe",
        Args["hour", int]["minute", int],
        Option(
            "-i|--incremental",
            dest="incremental",
            help_text="是否启用增量分析模式",
        ),
        alias={"订阅"},
        help_text="订阅当前群聊的定时分析 (需指定时 分)",
    ),
    Subcommand(
        "unsubscribe",
        alias={"取消订阅"},
        help_text="取消当前群聊的定时分析订阅",
    ),
    Subcommand(
        "list",
        alias={"列表", "ls"},
        help_text="查看所有分析订阅",
    ),
    meta=CommandMeta(
        description="群聊日常分析",
        usage=(
            "group_analysis [天数]\n"
            "group_analysis subscribe <时> <分>\n"
            "group_analysis unsubscribe\n"
            "group_analysis list"
        ),
        example=(
            "group_analysis\n"
            "group_analysis 3\n"
            "group_analysis subscribe 23 0\n"
            "group_analysis unsubscribe\n"
            "group_analysis list"
        ),
        author="wyf7685",
        fuzzy_match=True,
    ),
)
matcher = on_alconna(
    alc,
    priority=10,
    block=True,
    permission=TrustedUser(),
    aliases={"群分析"},
    extensions=[TelegramSlashExtension()],
    use_cmd_start=True,
)


# ── 订阅 ─────────────────────────────────────────────────


@matcher.assign("~subscribe")
async def assign_subscribe(
    arp: Arparma,
    session: Uninfo,
    target: MsgTarget,
    hour: int,
    minute: int,
) -> None:
    if target.private:
        await UniMessage.text("请在群聊中使用此命令").finish(reply_to=True)

    if not (0 <= hour < 24 and 0 <= minute < 60):
        await UniMessage.text("时间格式错误，请输入正确的时间 (0-23 0-59)").finish()

    incremental = arp.find("subscribe.incremental")
    sub = AnalysisSubscription(
        target_data=target.dump(),
        session_data=session,
        incremental_enabled=incremental,
    )
    add_subscription(sub)
    await UniMessage.text(
        f"已订阅每日 {hour:02d}:{minute:02d} 的群聊分析"
        f" (增量模式: {'启用' if incremental else '关闭'})\n"
        f"当前共 {len(subscriptions.load())} 个订阅"
    ).finish()


# ── 取消订阅 ─────────────────────────────────────────────


@matcher.assign("~unsubscribe")
async def assign_unsubscribe(target: MsgTarget) -> None:
    removed = remove_subscription(target)
    if removed:
        await UniMessage.text("已取消当前会话的分析订阅").finish()
    await UniMessage.text("当前会话没有分析订阅").finish()


# ── 列表 ─────────────────────────────────────────────────


@matcher.assign("~list")
async def assign_list(target: MsgTarget) -> None:
    subs = list_subscriptions()
    if not subs:
        await UniMessage.text("暂无分析订阅").finish()

    lines = ["📊 分析订阅列表:\n"]
    for i, sub in enumerate(subs, 1):
        scene = sub.session_data.scene
        name = scene.name or scene.id
        is_current = target.verify(sub.target)
        mark = " ✦" if is_current else ""
        lines.append(f"  {i}. {name} ({sub.analysis_days}天){mark}")
    await UniMessage.text("\n".join(lines)).finish()


# ── 手动分析 ──────────────────────────────────────────────


@matcher.handle()
async def handle_analysis(
    bot: Bot,
    session: Uninfo,
    target: MsgTarget,
    interface: Annotated[Interface | None, QueryInterface()],
    days: int | None = None,
) -> None:
    if target.private:
        await UniMessage.text("请在群聊中使用此命令").finish(reply_to=True)

    result = await run_daily_analysis(bot, session, days=days)

    if result is None:
        await UniMessage.text("未找到足够的群聊记录").finish(reply_to=True)

    await _send_report(result, interface)


# ── 报告发送调度 ─────────────────────────────────────────


async def _send_report(result: AnalysisResult, interface: Interface | None) -> None:
    """根据配置选择输出格式发送报告。图片失败时自动降级为文本。"""
    if config.output_format == "image" and interface is not None:
        image_bytes = await render_image(result, interface)
        if image_bytes:
            await UniMessage.image(raw=image_bytes).finish()
        # 图片渲染失败，降级文本
    await UniMessage.text(_format_text_report(result)).finish()


# ── 文本报告格式化 ───────────────────────────────────────


def _format_text_report(result: AnalysisResult) -> str:
    """生成纯文本格式的分析报告。"""
    lines = [
        f"📊 {result.group_name} 群聊分析报告",
        f"消息数: {result.statistics.message_count} | "
        f"参与者: {result.statistics.participant_count} | "
        f"活跃时段: {result.statistics.most_active_period}",
        "",
    ]

    if result.topics:
        lines.append("📌 话题总结:")
        for i, t in enumerate(result.topics, 1):
            lines.append(f"  {i}. {t.topic}")
            lines.append(f"     {t.detail}")
        lines.append("")

    if result.user_titles:
        lines.append("👤 用户画像:")
        lines.extend(
            f"  [{u.title}] {u.name} ({u.mbti}): {u.reason}" for u in result.user_titles
        )
        lines.append("")

    if result.golden_quotes:
        lines.append("💬 金句:")
        lines.extend(f"  「{q.content}」—— {q.sender}" for q in result.golden_quotes)
        lines.append("")

    if result.chat_quality:
        qr = result.chat_quality
        lines.append(f"📈 {qr.title}")
        lines.extend(
            f"  • {d.name} ({d.percentage:.0f}%): {d.comment}" for d in qr.dimensions
        )
        if qr.summary:
            lines.append(f"  总结: {qr.summary}")

    return "\n".join(lines)
