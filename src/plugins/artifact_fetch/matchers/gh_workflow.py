from typing import Annotated, Final, Protocol

import anyio
import anyio.lowlevel
from githubkit.typing import Missing
from nonebot import get_driver, logger, on_type
from nonebot.adapters.github.event import WorkflowRunCompleted, WorkflowRunRequested
from nonebot.params import Depends
from nonebot_plugin_alconna import UniMessage

from ..artifact_helper import ArtifactHelper
from ..config import AppGitHub
from ..data_source import (
    CacheDirectory,
    Repos,
    Subscription,
    get_cache_directory,
    subscriptions,
)
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
    app_github: AppGitHub,
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

    get_driver().task_group.start_soon(_track_workflow_run, app_github, event, sub)
    await UniMessage.text(msg).send(sub.target)


_tracking_runs: dict[int, anyio.Event] = {}


@get_driver().on_shutdown
async def _cleanup_tracking_runs() -> None:
    for run_id, stop_event in _tracking_runs.items():
        logger.info(f"Cleaning up tracking for workflow run {run_id}")
        stop_event.set()
    _tracking_runs.clear()
    await anyio.lowlevel.checkpoint()


async def _track_workflow_run(
    app_github: AppGitHub,
    event: WorkflowRunRequested,
    sub: Subscription,
) -> None:
    run_id = event.payload.workflow_run.id
    repo_name = event.payload.repository.full_name
    _tracking_runs[run_id] = stop_event = anyio.Event()

    async def wait_for_cancel() -> None:
        await stop_event.wait()
        tg.cancel_scope.cancel()

    async def get_run() -> WorkflowRunLike:
        response = await app_github.rest.actions.async_get_workflow_run(
            owner=sub.repos.owner, repo=sub.repos.repo, run_id=run_id
        )
        return response.parsed_data

    async def track_run_status() -> None:
        logger.info(f"Start tracking workflow run {run_id} in {repo_name}")
        while True:
            run = await get_run()
            logger.debug(f"Workflow run {run_id} status: {run.status}")
            if run.status == "completed":
                break
            await anyio.sleep(30)

        logger.success(f"Workflow run {run_id} in {repo_name} completed")
        logger.info("Waiting for on_completed handler to cancel...")
        await anyio.sleep(30)

        logger.warning("on_completed handler did not trigger")
        tg.start_soon(notify_workflow_run_completed, run, repo_name, sub)
        async with get_cache_directory() as cache_dir:
            await upload_artifacts_for_run(app_github, sub, run_id, cache_dir)

    async def wrapper() -> None:
        try:
            await track_run_status()
        except Exception:
            logger.exception("Error while tracking workflow run status")

    try:
        async with anyio.create_task_group() as tg:
            tg.start_soon(wait_for_cancel)
            tg.start_soon(wrapper)
    finally:
        if stop_event.is_set():
            logger.info("Tracking cancelled by on_completed handler")
        _tracking_runs.pop(event.payload.workflow_run.id, None)


class WorkflowRunLike(Protocol):
    id: Final[int]
    name: Final[Missing[str | None]]
    head_branch: Final[str | None]
    html_url: Final[str]
    status: Final[str | None]
    conclusion: Final[str | None]


async def notify_workflow_run_completed(
    run: WorkflowRunLike,
    repo_name: str,
    sub: Subscription,
) -> None:
    msg = (
        f"{'✅' if run.conclusion == 'success' else '❌'} Workflow 已完成\n"
        f"📦 仓库: {repo_name}\n"
        f"⚙️ 工作流: {run.name}\n"
        f"📊 状态: {run.conclusion}\n"
        f"🌿 分支: {run.head_branch}\n"
        f"🔗 链接: {run.html_url}"
    )
    await UniMessage.text(msg).send(sub.target)


async def upload_artifacts_for_run(
    app_github: AppGitHub,
    sub: Subscription,
    run_id: int,
    cache_dir: CacheDirectory,
) -> None:
    target = sub.target
    helper = await ArtifactHelper.from_owner_repo(app_github, *sub.repos)

    artifacts = await helper.fetch_artifacts(run_id)
    if not artifacts:
        await UniMessage.text("未找到工作流运行的任何 artifact").send(target)

    saved = await helper.download_artifacts(*artifacts, save_dir=cache_dir)
    if not saved:
        await UniMessage.text("未能成功下载任何 artifact").send(target)

    uploader = await get_upload_provider(target)
    async with anyio.create_task_group() as tg:
        for name, file in saved.items():
            tg.start_soon(uploader.upload, file, name, target, sub.extra)


@on_completed.handle()
async def handle_completed(
    event: WorkflowRunCompleted,
    sub: SubscriptionMatched,
) -> None:
    run = event.payload.workflow_run
    repo = event.payload.repository
    if run.id in _tracking_runs:
        _tracking_runs[run.id].set()

    await notify_workflow_run_completed(run, repo.full_name, sub)


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
    run_id = event.payload.workflow_run.id
    await upload_artifacts_for_run(app_github, sub, run_id, cache_dir)
