from typing import Annotated, Protocol

import anyio
import anyio.lowlevel
from githubkit.typing import Missing
from nonebot import get_driver, logger, on_type
from nonebot.adapters.github.event import WorkflowRunCompleted, WorkflowRunRequested
from nonebot.matcher import Matcher
from nonebot.params import Depends
from nonebot.rule import Rule
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
from ..upload import upload_artifacts


async def _workflow_run_repos(
    event: WorkflowRunRequested | WorkflowRunCompleted,
) -> Repos:
    repo_name = event.payload.repository.full_name
    owner, repo = repo_name.split("/", 1)
    return Repos(owner=owner, repo=repo)


async def _matching_sub(
    event: WorkflowRunRequested | WorkflowRunCompleted,
    repos: Annotated[Repos, Depends(_workflow_run_repos)],
) -> list[Subscription]:
    workflow_id = event.payload.workflow_run.workflow_id
    workflow_name = (
        event.payload.workflow and event.payload.workflow.path.rsplit("/", 1)[-1]
    )
    matched: list[Subscription] = []
    for sub in subscriptions.load():
        if sub.repos != repos:
            continue
        match sub.workflow_id:
            case None:
                matched.append(sub)
            case int() as wid if wid == workflow_id:
                matched.append(sub)
            case str() as wname if workflow_name is not None and wname == workflow_name:
                matched.append(sub)
    return matched


@Rule
async def _is_subscribed(
    sub: Annotated[list[Subscription], Depends(_matching_sub)],
) -> bool:
    return bool(sub)


SubscriptionMatched = Annotated[list[Subscription], Depends(_matching_sub)]


async def _get_artifact_helper(
    app_github: AppGitHub,
    subs: SubscriptionMatched,
) -> ArtifactHelper:
    if not subs:
        Matcher.skip()
    owner, repo = subs[0].repos
    try:
        return await ArtifactHelper.from_owner_repo(app_github, owner, repo)
    except Exception:
        logger.opt(exception=True).warning(
            f"Failed to create ArtifactHelper for {owner}/{repo}"
        )
        Matcher.skip()


Helper = Annotated[ArtifactHelper, Depends(_get_artifact_helper)]


on_requested = on_type(WorkflowRunRequested, rule=_is_subscribed)
on_completed = on_type(WorkflowRunCompleted, rule=_is_subscribed)


@on_requested.handle()
async def handle_requested(
    helper: Helper,
    event: WorkflowRunRequested,
    subs: SubscriptionMatched,
) -> None:
    run = event.payload.workflow_run
    repo = event.payload.repository
    run_id = run.id

    msg = (
        f"🚀 Workflow 已启动\n"
        f"📦 仓库: {repo.full_name}\n"
        f"⚙️ 工作流: {run.name}\n"
        f"🌿 分支: {run.head_branch}\n"
        f"💬 提交: {run.head_commit.message}\n"
        f"🔗 链接: {run.html_url}"
    )

    if run_id not in _tracking_runs:
        stop_event = anyio.Event()
        _tracking_runs[run_id] = stop_event
        get_driver().task_group.start_soon(
            _track_workflow_run,
            helper,
            list(subs),
            run_id,
            repo.full_name,
            stop_event,
        )
        for sub in subs:
            try:
                await UniMessage.text(msg).send(sub.target)
            except Exception:
                logger.exception(
                    f"Failed to notify workflow run {run_id} start for {sub.target}"
                )


_tracking_runs: dict[int, anyio.Event] = {}


@get_driver().on_shutdown
async def _cleanup_tracking_runs() -> None:
    for run_id, stop_event in _tracking_runs.items():
        logger.info(f"Cleaning up tracking for workflow run {run_id}")
        stop_event.set()
    _tracking_runs.clear()
    await anyio.lowlevel.checkpoint()


async def _track_workflow_run(
    helper: Helper,
    subs: list[Subscription],
    run_id: int,
    repo_name: str,
    stop_event: anyio.Event,
) -> None:
    async def wait_for_cancel() -> None:
        await stop_event.wait()
        tg.cancel_scope.cancel()

    async def get_run() -> WorkflowRunLike:
        response = await helper.github.rest.actions.async_get_workflow_run(
            owner=subs[0].repos.owner, repo=subs[0].repos.repo, run_id=run_id
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
        for sub in subs:
            try:
                await notify_workflow_run_completed(run, repo_name, sub)
            except Exception:
                logger.exception(
                    "Failed to notify workflow run "
                    f"{run_id} completion for {sub.target}"
                )
        for sub in subs:
            if sub.artifact_upload_config is None:
                continue
            try:
                async with get_cache_directory() as cache_dir:
                    await upload_artifacts_for_run(helper, sub, run_id, cache_dir)
            except Exception:
                logger.exception(
                    f"Failed to upload artifacts for workflow run {run_id} "
                    f"to {sub.target}"
                )

    async def wrapper() -> None:
        try:
            await track_run_status()
        except Exception:
            logger.exception("Error while tracking workflow run status")
            tg.cancel_scope.cancel()

    try:
        async with anyio.create_task_group() as tg:
            tg.start_soon(wait_for_cancel)
            tg.start_soon(wrapper)
    finally:
        if stop_event.is_set():
            logger.info("Tracking cancelled by on_completed handler")
        if _tracking_runs.get(run_id) is stop_event:
            _tracking_runs.pop(run_id, None)


class WorkflowRunLike(Protocol):
    @property
    def id(self) -> int: ...
    @property
    def name(self) -> Missing[str | None]: ...
    @property
    def head_branch(self) -> str | None: ...
    @property
    def html_url(self) -> str: ...
    @property
    def status(self) -> str | None: ...
    @property
    def conclusion(self) -> str | None: ...


async def notify_workflow_run_completed(
    run: WorkflowRunLike,
    repo_name: str,
    sub: Subscription,
) -> None:
    msg = (
        f"{"✅" if run.conclusion == "success" else "❌"} Workflow 已完成\n"
        f"📦 仓库: {repo_name}\n"
        f"⚙️ 工作流: {run.name}\n"
        f"🌿 分支: {run.head_branch}\n"
        f"📊 状态: {run.conclusion}\n"
        f"🔗 链接: {run.html_url}"
    )
    await UniMessage.text(msg).send(sub.target)


async def upload_artifacts_for_run(
    helper: Helper,
    sub: Subscription,
    run_id: int,
    cache_dir: CacheDirectory,
) -> None:
    target = sub.target
    assert sub.artifact_upload_config is not None
    cfg = sub.artifact_upload_config

    try:
        artifacts = await helper.fetch_artifacts(run_id)
    except Exception:
        logger.exception(f"Failed to fetch artifacts for workflow run {run_id}")
        await UniMessage.text("获取工作流 artifact 失败").send(target)
        return
    if not artifacts:
        await UniMessage.text("未找到工作流运行的任何 artifact").send(target)
        return

    filtered_artifacts = [
        artifact for artifact in artifacts if cfg.match_regex(artifact.name)
    ]
    if not filtered_artifacts:
        await UniMessage.text("没有 artifact 符合过滤条件").send(target)
        return

    try:
        run_resp = await helper.github.rest.actions.async_get_workflow_run(
            owner=sub.repos.owner, repo=sub.repos.repo, run_id=run_id
        )
        saved = await helper.download_artifacts(
            *filtered_artifacts,
            save_dir=cache_dir,
            run=run_resp.parsed_data,
            config=cfg,
        )
    except Exception:
        logger.exception(f"Failed to download artifacts for workflow run {run_id}")
        await UniMessage.text("下载工作流 artifact 失败").send(target)
        return
    if not saved:
        await UniMessage.text("未能成功下载任何 artifact").send(target)
        return

    await upload_artifacts(
        saved,
        target,
        key_prefix=f"artifacts/{sub.owner}/{sub.repo}/{run_id}",
    )


@on_completed.handle()
async def handle_completed(
    event: WorkflowRunCompleted,
    subs: SubscriptionMatched,
) -> None:
    run = event.payload.workflow_run
    repo = event.payload.repository
    if run.id in _tracking_runs:
        _tracking_runs[run.id].set()

    for sub in subs:
        try:
            await notify_workflow_run_completed(run, repo.full_name, sub)
        except Exception:
            logger.exception(
                f"Failed to notify workflow run {run.id} completion for {sub.target}"
            )


async def _check_upload_artifact(subs: SubscriptionMatched) -> None:
    if not any(sub.artifact_upload_config is not None for sub in subs):
        on_completed.skip()


@on_completed.handle(parameterless=[Depends(_check_upload_artifact)])
async def handle_completed_with_artifact(
    event: WorkflowRunCompleted,
    helper: Helper,
    subs: SubscriptionMatched,
    cache_dir: CacheDirectory,
) -> None:
    run_id = event.payload.workflow_run.id
    for sub in subs:
        if sub.artifact_upload_config is None:
            continue
        try:
            await upload_artifacts_for_run(helper, sub, run_id, cache_dir)
        except Exception:
            logger.exception(
                f"Failed to upload artifacts for workflow run {run_id} to {sub.target}"
            )
