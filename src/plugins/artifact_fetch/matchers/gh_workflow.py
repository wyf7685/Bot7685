from typing import Annotated

import anyio
from nonebot import on_type
from nonebot.adapters.github.event import WorkflowRunCompleted, WorkflowRunRequested
from nonebot.params import Depends
from nonebot_plugin_alconna import UniMessage

from ..artifact_helper import ArtifactHelper
from ..config import AppGitHub
from ..data_source import CacheDirectory, Repos, Subscription, subscriptions
from ..upload import get_upload_provider


async def _workflow_run_repos(
    event: WorkflowRunRequested | WorkflowRunCompleted,
) -> Repos:
    repo_name = event.payload.repository.full_name
    owner, repo = repo_name.split("/", 1)
    return Repos(owner=owner, repo=repo)


WorkflowRunRepos = Annotated[Repos, Depends(_workflow_run_repos)]


async def _matching_sub(
    event: WorkflowRunRequested | WorkflowRunCompleted,
    repos: WorkflowRunRepos,
) -> Subscription | None:
    workflow_id = event.payload.workflow_run.workflow_id
    workflow_name = (
        event.payload.workflow and event.payload.workflow.path.rsplit("/", 1)[-1]
    )
    for sub in subscriptions.load():
        if sub.repos != repos:
            continue
        match sub.workflow_id:
            case None:
                return sub
            case int() as wid if wid == workflow_id:
                return sub
            case str() as wname if workflow_name is not None and wname == workflow_name:
                return sub
    return None


async def _is_subscribed(
    sub: Annotated[Subscription | None, Depends(_matching_sub)],
) -> bool:
    return sub is not None


SubscriptionMatched = Annotated[Subscription, Depends(_matching_sub)]


on_requested = on_type(WorkflowRunRequested, rule=_is_subscribed)
on_completed = on_type(WorkflowRunCompleted, rule=_is_subscribed)


@on_requested.handle()
async def handle_requested(
    event: WorkflowRunRequested,
    sub: SubscriptionMatched,
) -> None:
    run = event.payload.workflow_run
    repo = event.payload.repository

    msg = (
        f"🚀 Workflow 已启动\n"
        f"📦 仓库: {repo.full_name}\n"
        f"⚙️ 工作流: {run.name}\n"
        f"🌿 分支: {run.head_branch}\n"
        f"💬 提交: {run.head_commit.message}\n"
        f"🔗 链接: {run.html_url}"
    )

    await UniMessage.text(msg).send(sub.target)


@on_completed.handle()
async def handle_completed(
    event: WorkflowRunCompleted,
    sub: SubscriptionMatched,
) -> None:
    run = event.payload.workflow_run
    repo = event.payload.repository

    msg = (
        f"{'✅' if run.conclusion == 'success' else '❌'} Workflow 已完成\n"
        f"📦 仓库: {repo.full_name}\n"
        f"⚙️ 工作流: {run.name}\n"
        f"📊 状态: {run.conclusion}\n"
        f"🌿 分支: {run.head_branch}\n"
        f"🔗 链接: {run.html_url}"
    )

    await UniMessage.text(msg).send(sub.target)


async def _check_upload_artifact(sub: SubscriptionMatched) -> None:
    if not sub.upload_artifact:
        on_completed.skip()


@on_completed.handle(parameterless=[Depends(_check_upload_artifact)])
async def handle_completed_with_artifact(
    app_github: AppGitHub,
    event: WorkflowRunCompleted,
    sub: SubscriptionMatched,
    cache_dir: CacheDirectory,
) -> None:
    target = sub.target
    helper = await ArtifactHelper.from_owner_repo(app_github, *sub.repos)

    artifacts = await helper.fetch_artifacts(event.payload.workflow_run.id)
    if not artifacts:
        await UniMessage.text("未找到工作流运行的任何 artifact").send(target)

    saved = await helper.download_artifacts(*artifacts, save_dir=cache_dir)
    if not saved:
        await UniMessage.text("未能成功下载任何 artifact").send(target)

    uploader = await get_upload_provider(target)
    async with anyio.create_task_group() as tg:
        for name, file in saved.items():
            tg.start_soon(uploader.upload, file, name, target, sub.extra)
