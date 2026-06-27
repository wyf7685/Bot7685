import contextlib
import hashlib
from collections.abc import Buffer
from pathlib import Path
from typing import TYPE_CHECKING, Annotated, Any, Self

import anyio
import anyio.lowlevel
import ayafileio
import httpx
from githubkit.exception import RequestFailed
from githubkit.versions.latest.models import Artifact, Workflow, WorkflowRun
from nonebot import logger
from nonebot.params import Depends
from nonebot.utils import escape_tag
from nonebot_plugin_alconna import UniMessage

from src.utils import with_semaphore

from .config import AppGitHub, plugin_config
from .data_source import ArtifactConfig, WorkflowID
from .depends import Repository

if TYPE_CHECKING:
    from githubkit import AppAuthStrategy, AppInstallationAuthStrategy, GitHub


async def download_artifact(
    client: httpx.AsyncClient,
    artifact: Artifact,
    save_path: Path,
    chunk_size: int = plugin_config.download.chunk_size,
    concurrency_limit: int = plugin_config.download.concurrency_limit,
    chunk_max_retry: int = plugin_config.download.chunk_max_retry,
) -> None:
    chunk_send, chunk_recv = anyio.create_memory_object_stream[tuple[int, Buffer]](
        max_buffer_size=concurrency_limit * 2
    )
    total_size = artifact.size_in_bytes
    total_chunks = (total_size + chunk_size - 1) // chunk_size
    colored_name = f"<le>{escape_tag(artifact.name)}</>"

    def format_progress(
        bytes_written: int,
        chunk_count: int,
        current_time: float,
    ) -> str:
        progress_percentage = bytes_written / total_size * 100
        time_elapsed = current_time - time_start
        avg_speed = bytes_written / time_elapsed if time_elapsed > 0 else 0
        remaining_bytes = total_size - bytes_written
        time_remaining = remaining_bytes / avg_speed if avg_speed > 0 else float("inf")
        return (
            f"{colored_name}: "
            f"Wrote chunk <c>{chunk_count}</>/<c>{total_chunks}</>"
            f" (<c>{bytes_written}</> bytes, <g>{progress_percentage:.2f}</>%)"
            f" | avg: <c>{avg_speed / (1024 * 1024):.2f}</> MB/s"
            f" | eta: <c>{time_remaining:.2f}</> seconds"
        )

    async def file_writer(file: ayafileio.AsyncFile[bytes]) -> None:
        await file.truncate(total_size)  # pre-allocate file size

        chunk_count = bytes_written = 0
        async for offset, chunk in chunk_recv:
            data = memoryview(chunk)
            await file.seek(offset)
            await file.write(data)
            chunk_count += 1
            bytes_written += len(data)

            if chunk_count % 10 == 0 or chunk_count == total_chunks:
                logger.opt(colors=True).debug(
                    format_progress(bytes_written, chunk_count, anyio.current_time())
                )

    @with_semaphore(concurrency_limit)
    async def request_chunk(chunk_range: str) -> Buffer:
        buffer = bytearray()
        async with client.stream(
            method="GET",
            url=artifact.archive_download_url,
            headers={"Range": f"bytes={chunk_range}"},
        ) as response:
            response.raise_for_status()
            async for chunk in response.aiter_bytes():
                buffer.extend(chunk)
        return buffer

    async def fetch_chunk_with_retry(chunk_seq: int) -> None:
        start = chunk_seq * chunk_size
        end = min(start + chunk_size - 1, total_size - 1)
        chunk_range = f"{start}-{end}"

        excs: list[Exception] = []
        for attempt in range(1, chunk_max_retry + 1):
            try:
                buffer = await request_chunk(chunk_range)
            except Exception as e:
                logger.opt(
                    colors=True,
                    exception=not isinstance(e, httpx.HTTPError),
                ).warning(
                    f"{colored_name}: Error downloading chunk:"
                    f" seq=<c>{chunk_seq}</>, range=<c>{chunk_range}</>"
                    f" (attempt <y>{attempt}</>/<g>{chunk_max_retry}</>)"
                    f" - <r>{escape_tag(repr(e))}</>"
                )
                excs.append(e)
                if attempt == chunk_max_retry:
                    raise ExceptionGroup(
                        f"Failed to download chunk seq={chunk_seq}"
                        f" after {chunk_max_retry} attempts",
                        excs,
                    ) from None
            else:
                await chunk_send.send((start, buffer))
                return

    async def fetch_chunks() -> None:
        async with chunk_send, anyio.create_task_group() as tg:
            for seq in range(total_chunks):
                tg.start_soon(fetch_chunk_with_retry, seq)
                await anyio.lowlevel.checkpoint()

    logger.opt(colors=True).info(
        f"{colored_name}: "
        f"Starting download of <y>{total_size}</> bytes (<g>{total_chunks}</> chunks) "
        f"from <c><u>{artifact.archive_download_url}</></>"
    )
    time_start = anyio.current_time()
    async with ayafileio.open(save_path, "wb") as file, anyio.create_task_group() as tg:
        tg.start_soon(file_writer, file)
        tg.start_soon(fetch_chunks)

    time_end = anyio.current_time()
    time_elapsed = time_end - time_start
    speed_mb = total_size / time_elapsed / (1024 * 1024)

    logger.opt(colors=True).info(
        f"{colored_name}: Download completed in <g>{time_elapsed:.2f}</> seconds"
    )
    logger.opt(colors=True).info(
        f"{colored_name}: Average speed: <c>{speed_mb:.2f}</>MB/s"
    )

    if artifact.digest and artifact.digest.startswith("sha256:"):
        expected_hash = artifact.digest.removeprefix("sha256:")
        sha = hashlib.sha256()
        async with ayafileio.open(save_path, "rb") as f:
            while chunk := await f.read(10 * 1024 * 1024):  # read in 10 MB chunks
                sha.update(chunk)
        actual_hash = sha.hexdigest()
        logger.opt(colors=True).debug(
            f"{colored_name}: "
            f"Expected SHA256: <c>{expected_hash}</>, "
            f"Actual SHA256: <c>{actual_hash}</>"
        )
        if actual_hash != expected_hash:
            raise ValueError("Downloaded artifact digest does not match expected value")


def prepare_format_data(config: ArtifactConfig, artifact: Artifact) -> dict[str, Any]:
    match = config.match_regex(artifact.name)
    data: dict[str, Any] = {"artifact": artifact, "match": match}
    if match is not None:
        data["$0"] = match.group(0)
        data.update({f"${i}": g for i, g in enumerate(match.groups(), start=1)})
    return data


class ArtifactHelper:
    def __init__(
        self,
        owner: str,
        repo: str,
        github: GitHub[AppInstallationAuthStrategy],
    ) -> None:
        self.owner = owner
        self.repo = repo
        self.github = github

    @classmethod
    async def from_owner_repo(
        cls,
        app_github: GitHub[AppAuthStrategy],
        owner: str,
        repo: str,
    ) -> Self:
        resp = await app_github.rest.apps.async_get_repo_installation(
            owner=owner, repo=repo
        )
        installation_id = resp.parsed_data.id
        installation_github = app_github.with_auth(
            app_github.auth.as_installation(installation_id)
        )
        return cls(owner, repo, installation_github)

    async def get_workflow(self, workflow_id: WorkflowID) -> Workflow | None:
        try:
            response = await self.github.rest.actions.async_get_workflow(
                owner=self.owner,
                repo=self.repo,
                workflow_id=workflow_id,
            )
        except RequestFailed as exc:
            if exc.response.status_code == 404:
                return None
            raise
        else:
            return response.parsed_data

    async def fetch_latest_run(
        self,
        workflow_id: int | str | None = None,
    ) -> WorkflowRun:
        response = (
            await self.github.rest.actions.async_list_workflow_runs(
                owner=self.owner,
                repo=self.repo,
                workflow_id=workflow_id,
                per_page=1,
            )
            if workflow_id is not None
            else await self.github.rest.actions.async_list_workflow_runs_for_repo(
                owner=self.owner,
                repo=self.repo,
                per_page=1,
            )
        )
        data = response.parsed_data
        if data.total_count == 0:
            raise ValueError("No workflow runs found")
        return data.workflow_runs[0]

    async def fetch_artifacts(self, run_id: int) -> list[Artifact]:
        response = await self.github.rest.actions.async_list_workflow_run_artifacts(
            owner=self.owner,
            repo=self.repo,
            run_id=run_id,
        )
        return response.parsed_data.artifacts

    async def download_artifacts(
        self,
        *artifacts: Artifact,
        save_dir: Path,
        run: WorkflowRun | None = None,
        config: ArtifactConfig | None = None,
    ) -> dict[str, Path]:
        saved: dict[str, Path] = {}
        format_data = (
            {"run": run, "head_sha": run.head_sha, "head_sha_short": run.head_sha[:7]}
            if run
            else {}
        )

        async def download(client: httpx.AsyncClient, artifact: Artifact) -> None:
            save_path = save_dir / f"{artifact.name}.zip"
            try:
                await download_artifact(client, artifact, save_path)
            except Exception:
                logger.exception(f"Failed to download artifact {artifact.name}")
                with contextlib.suppress(Exception):
                    await anyio.Path(save_path).unlink(missing_ok=True)
                return

            if config is not None:
                name = config.rename(
                    artifact.name,
                    {**format_data, **prepare_format_data(config, artifact)},
                )
            else:
                name = artifact.name
            saved[f"{name}.zip"] = save_path

        await anyio.Path(save_dir).mkdir(parents=True, exist_ok=True)
        async with (
            self.github.get_async_client() as client,
            anyio.create_task_group() as tg,
        ):
            for artifact in artifacts:
                tg.start_soon(download, client, artifact)

        return saved


async def _artifact_helper(
    app_github: AppGitHub,
    repository: Repository,
) -> ArtifactHelper:
    owner, repo = repository

    try:
        return await ArtifactHelper.from_owner_repo(app_github, owner, repo)
    except RequestFailed as exc:
        if exc.response.status_code != 404:
            logger.error(f"Failed to create ArtifactHelper: {exc.response.text}")
            raise

        logger.warning(
            f"Failed to create ArtifactHelper: No installation found for {owner}/{repo}"
        )
        await UniMessage.text(
            f"无法访问仓库 {owner}/{repo}\n请确保已安装 GitHub App 并授权访问该仓库"
        ).finish(reply_to=True)


Helper = Annotated[ArtifactHelper, Depends(_artifact_helper)]


async def _requested_run(
    helper: Helper,
    workflow_id: WorkflowID | None = None,
) -> WorkflowRun:
    try:
        return await helper.fetch_latest_run(workflow_id)
    except Exception as exc:
        logger.exception("Failed to fetch latest workflow run")
        await UniMessage.text(f"获取最新工作流运行失败: {exc}").finish(reply_to=True)


RequestedRun = Annotated[WorkflowRun, Depends(_requested_run)]


async def _requested_artifacts(
    helper: Helper,
    run: RequestedRun,
) -> list[Artifact]:
    try:
        artifacts = await helper.fetch_artifacts(run.id)
    except Exception as exc:
        logger.exception("Failed to fetch artifacts")
        await UniMessage.text(f"获取 artifact 失败: {exc}").finish(reply_to=True)

    if not artifacts:
        await UniMessage.text("未找到最新工作流运行的任何 artifact").finish(
            reply_to=True
        )
    return artifacts


RequestedArtifacts = Annotated[list[Artifact], Depends(_requested_artifacts)]
