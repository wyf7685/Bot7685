from typing import Annotated

from nonebot import logger
from nonebot.adapters import Bot
from nonebot.params import Depends
from nonebot_plugin_alconna import (
    Alconna,
    Args,
    CustomNode,
    MsgTarget,
    Option,
    Subcommand,
    SupportScope,
    UniMessage,
    on_alconna,
)
from nonebot_plugin_uninfo import Uninfo
from pydantic import ValidationError

from src.service.uninfo_target import persist_session_reference

from ..artifact_helper import Helper, RequestedArtifacts, RequestedRun
from ..data_source import (
    ArtifactConfig,
    CacheDirectory,
    Subscription,
    WorkflowID,
    add_subscription,
    list_subscriptions,
    remove_subscription,
    subscription_exists,
)
from ..depends import Repository
from ..upload import upload_artifacts

alc = Alconna(
    "artifact",
    Subcommand(
        "fetch",
        Option("--owner|-o", Args["owner", str]),
        Option("--repo|-r", Args["repo", str]),
        Option("--workflow-id|-w", Args["workflow_id?", WorkflowID]),
    ),
    Subcommand(
        "subscribe",
        Subcommand(
            "add",
            Option("--owner|-o", Args["owner", str]),
            Option("--repo|-r", Args["repo", str]),
            Option("--workflow-id|-w", Args["workflow_id?", WorkflowID]),
            Option("--upload-artifact", dest="upload_artifact"),
            Option("--filter-regex", Args["filter_regex?", str]),
            Option("--rename-template", Args["rename_template?", str]),
        ),
        Subcommand(
            "remove",
            Option("--owner|-o", Args["owner", str]),
            Option("--repo|-r", Args["repo", str]),
            Option("--workflow-id|-w", Args["workflow_id?", WorkflowID]),
            alias={"rm"},
        ),
        Subcommand("list", alias={"ls"}),
        alias={"sub"},
    ),
)
matcher = on_alconna(alc)


@matcher.assign("~fetch")
async def assign_fetch(
    helper: Helper,
    run: RequestedRun,
    artifacts: RequestedArtifacts,
    cache_dir: CacheDirectory,
) -> None:
    saved = await helper.download_artifacts(*artifacts, save_dir=cache_dir)
    if not saved:
        await UniMessage.text("未能成功下载任何 artifact").finish(reply_to=True)

    await upload_artifacts(
        saved,
        target=None,
        reply_to=True,
        key_prefix=f"artifacts/{helper.owner}/{helper.repo}/{run.id}",
    )


async def _extract_sub(
    session: Uninfo,
    repos: Repository,
    workflow_id: WorkflowID | None = None,
) -> Subscription:
    ref = await persist_session_reference(session)
    return Subscription.create(
        session_persist_id=ref.session_persist_id,
        scene_persist_id=ref.scene_persist_id,
        owner=repos.owner,
        repo=repos.repo,
        workflow_id=workflow_id,
    )


async def _verify_new_sub(
    new_sub: Annotated[Subscription, Depends(_extract_sub)],
    helper: Helper,
    workflow_id: WorkflowID | None = None,
) -> Subscription:
    if await subscription_exists(new_sub):
        await UniMessage.text("已存在相同订阅").finish(reply_to=True)

    if workflow_id is not None:
        workflow = await helper.get_workflow(workflow_id)
        if workflow is None:
            await UniMessage.text(f"未找到 ID 为 {workflow_id} 的工作流").finish(
                reply_to=True
            )

    return new_sub


@matcher.assign("~subscribe.add.upload_artifact")
async def assign_subscribe_add_upload(
    sub: Annotated[Subscription, Depends(_verify_new_sub)],
    filter_regex: str | None = None,
    rename_template: str | None = None,
) -> None:
    try:
        config = ArtifactConfig(
            filter_regex=filter_regex,
            rename_template=rename_template,
        )
    except ValidationError:
        await UniMessage.text("过滤正则或重命名模板无效").finish(reply_to=True)
    sub.artifact_upload_config = config


@matcher.assign("~subscribe.add")
async def assign_subscribe_add(
    sub: Annotated[Subscription, Depends(_verify_new_sub)],
) -> None:
    await add_subscription(sub)
    logger.info(f"Added subscription: {sub!r}")
    msg = (
        f"已订阅仓库 {sub.owner}/{sub.repo} 的工作流"
        f"{f"（ID: {sub.workflow_id}）" if sub.workflow_id else ""}"
        "的运行状态更新"
    )
    if cfg := sub.artifact_upload_config:
        msg += "\n\nArtifact 上传配置:\n"
        msg += f"- 过滤正则: {cfg.filter_regex or "<未配置>"}\n"
        msg += f"- 重命名模板: {cfg.rename_template or "<未配置>"}\n"
    await UniMessage.text(msg).finish(reply_to=True)


@matcher.assign("~subscribe.remove")
async def assign_subscribe_remove(
    sub: Annotated[Subscription, Depends(_extract_sub)],
) -> None:
    if await remove_subscription(sub):
        logger.info(f"Removed subscription: {sub!r}")
        msg = (
            f"已取消订阅仓库 {sub.owner}/{sub.repo} 的工作流"
            + (f"（ID: {sub.workflow_id}）" if sub.workflow_id else "")
            + "的运行状态更新"
        )
        await UniMessage.text(msg).finish(reply_to=True)

    await UniMessage.text("未找到匹配的订阅").finish(reply_to=True)


@matcher.assign("~subscribe.list")
async def assign_subscribe_list(
    bot: Bot,
    session: Uninfo,
    target: MsgTarget,
) -> None:
    ref = await persist_session_reference(session)
    subs = await list_subscriptions(scene_persist_id=ref.scene_persist_id)
    if not subs:
        await UniMessage.text("当前会话没有任何订阅").finish(reply_to=True)

    msgs: list[str] = []
    for sub in subs:
        msg = (
            f"- 仓库: {sub.owner}/{sub.repo}\n"
            f"  工作流{f" ID: {sub.workflow_id}" if sub.workflow_id else ": 全部"}\n"
        )
        if cfg := sub.artifact_upload_config:
            msg += "  Artifact 上传配置:\n"
            msg += f"    - 过滤正则: {cfg.filter_regex or "<未配置>"}\n"
            msg += f"    - 重命名模板: {cfg.rename_template or "<未配置>"}\n"
        msgs.append(msg.strip())

    if not msgs:
        await UniMessage.text("当前会话没有任何订阅").finish(reply_to=True)

    summary = f"当前会话共有 {len(msgs)} 条订阅"
    if target.scope == SupportScope.qq_client:
        summary_node = CustomNode(
            uid=bot.self_id,
            name="订阅列表 - 标题",
            content=summary,
            context=target.id,
        )
        nodes = [
            CustomNode(
                uid=bot.self_id,
                name=f"订阅列表 - {idx}",
                content=msg,
                context=target.id,
            )
            for idx, msg in enumerate(msgs, 1)
        ]
        await UniMessage.reference(summary_node, *nodes).finish()
    else:
        await UniMessage.text("\n\n".join([summary, *msgs])).finish(reply_to=True)
