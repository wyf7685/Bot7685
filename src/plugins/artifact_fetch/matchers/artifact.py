from typing import Annotated

import anyio
from nonebot import logger
from nonebot.params import Depends
from nonebot_plugin_alconna import (
    Alconna,
    Args,
    MsgTarget,
    Option,
    Subcommand,
    UniMessage,
    on_alconna,
)

from ..artifact_helper import Helper, RequestedArtifacts
from ..data_source import (
    ArtifactConfig,
    CacheDirectory,
    Subscription,
    WorkflowID,
    subscriptions,
)
from ..depends import Repository
from ..upload import Uploader, UploaderExtra

alc = Alconna(
    "artifact",
    Subcommand(
        "fetch",
        Option("--owner|-o", Args["owner", str]),
        Option("--repo|-r", Args["repo", str]),
        Option("--workflow-id|-w", Args["workflow_id?", WorkflowID]),
        Option("--target-folder|-t", Args["target_folder?", str]),
    ),
    Subcommand(
        "subscribe",
        Subcommand(
            "add",
            Option("--owner|-o", Args["owner", str]),
            Option("--repo|-r", Args["repo", str]),
            Option("--workflow-id|-w", Args["workflow_id?", WorkflowID]),
            Option("--upload-artifact", dest="upload_artifact"),
            Option("--target-folder|-t", Args["target_folder?", str]),
            Option("--filter-regex", Args["filter_regex?", str]),
            Option("--rename-template", Args["rename_template?", str]),
        ),
        Subcommand(
            "remove",
            Option("--owner|-o", Args["owner", str]),
            Option("--repo|-r", Args["repo", str]),
            Option("--workflow-id|-w", Args["workflow_id?", WorkflowID]),
        ),
        alias={"sub"},
    ),
)
matcher = on_alconna(alc)


@matcher.assign("~fetch")
async def assign_fetch(
    target: MsgTarget,
    helper: Helper,
    artifacts: RequestedArtifacts,
    cache_dir: CacheDirectory,
    uploader: Uploader,
    uploader_extra: UploaderExtra,
) -> None:
    saved = await helper.download_artifacts(*artifacts, save_dir=cache_dir)
    if not saved:
        await UniMessage.text("未能成功下载任何 artifact").finish(reply_to=True)

    async with anyio.create_task_group() as tg:
        for name, file in saved.items():
            tg.start_soon(uploader.upload, file, name, target, uploader_extra)


async def _extract_sub(
    target: MsgTarget,
    repos: Repository,
    workflow_id: WorkflowID | None = None,
) -> Subscription:
    return Subscription(
        owner=repos.owner,
        repo=repos.repo,
        workflow_id=workflow_id,
        target_data=target.dump(),
    )


async def _verify_new_sub(
    new_sub: Annotated[Subscription, Depends(_extract_sub)],
    helper: Helper,
    workflow_id: WorkflowID | None = None,
) -> Subscription:
    for sub in subscriptions.load():
        if sub.verify(new_sub):
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
    uploader_extra: UploaderExtra,
    filter_regex: str | None = None,
    rename_template: str | None = None,
) -> None:
    sub.artifact_upload_config = ArtifactConfig(
        filter_regex=filter_regex,
        rename_template=rename_template,
        extra=uploader_extra,
    )
    logger.debug(f"Extracted extra for subscription: {uploader_extra!r}")


@matcher.assign("~subscribe.add")
async def assign_subscribe_add(
    sub: Annotated[Subscription, Depends(_verify_new_sub)],
) -> None:
    subscriptions.add(sub)
    logger.info(f"Added subscription: {sub!r}")
    msg = (
        f"已订阅仓库 {sub.owner}/{sub.repo} 的工作流"
        f"{f'（ID: {sub.workflow_id}）' if sub.workflow_id else ''}"
        "的运行状态更新"
    )
    if cfg := sub.artifact_upload_config:
        msg += "\n\nArtifact 上传配置:\n"
        msg += f"- 过滤正则: {cfg.filter_regex or '<未配置>'}\n"
        msg += f"- 重命名模板: {cfg.rename_template or '<未配置>'}\n"
    await UniMessage.text(msg).finish(reply_to=True)


@matcher.assign("~subscribe.remove")
async def assign_subscribe_remove(
    sub: Annotated[Subscription, Depends(_extract_sub)],
) -> None:
    for existing in subscriptions.load()[:]:
        if existing.verify(sub):
            subscriptions.remove(existing.verify)
            logger.info(f"Removed subscription: {existing!r}")
            msg = (
                f"已取消订阅仓库 {sub.owner}/{sub.repo} 的工作流"
                + (f"（ID: {sub.workflow_id}）" if sub.workflow_id else "")
                + "的运行状态更新"
            )
            await UniMessage.text(msg).finish(reply_to=True)

    await UniMessage.text("未找到匹配的订阅").finish(reply_to=True)
