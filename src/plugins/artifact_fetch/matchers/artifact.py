from typing import Annotated

import anyio
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
from ..data_source import CacheDirectory, Subscription, WorkflowID, subscriptions
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
        Option("--owner|-o", Args["owner", str]),
        Option("--repo|-r", Args["repo", str]),
        Option("--workflow-id|-w", Args["workflow_id?", WorkflowID]),
        Option("--upload-artifact", dest="upload_artifact"),
        Option("--target-folder|-t", Args["target_folder?", str]),
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


async def _build_sub(
    target: MsgTarget,
    repos: Repository,
    helper: Helper,
    workflow_id: WorkflowID | None = None,
) -> Subscription:
    for sub in subscriptions.load():
        if sub.repos == repos and sub.workflow_id == workflow_id:
            await UniMessage.text("已存在相同订阅").finish(reply_to=True)

    if workflow_id is not None:
        workflow = await helper.get_workflow(workflow_id)
        if workflow is None:
            await UniMessage.text(f"未找到 ID 为 {workflow_id} 的工作流").finish(
                reply_to=True
            )

    return Subscription(
        owner=repos.owner,
        repo=repos.repo,
        workflow_id=workflow_id,
        target_data=target.dump(),
    )


NewSubscription = Annotated[Subscription, Depends(_build_sub)]


@matcher.assign("~subscribe.upload_artifact")
async def assign_subscribe_upload(
    sub: NewSubscription,
    uploader_extra: UploaderExtra,
) -> None:
    sub.upload_artifact = True
    sub.extra = uploader_extra


@matcher.assign("~subscribe")
async def assign_subscribe(sub: NewSubscription) -> None:
    subscriptions.add(sub)
    msg = (
        f"已订阅仓库 {sub.owner}/{sub.repo} 的工作流"
        + (f"（ID: {sub.workflow_id}）" if sub.workflow_id else "")
        + "的运行状态更新"
    )
    await UniMessage.text(msg).finish(reply_to=True)
