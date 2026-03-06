import contextlib
import hashlib
from collections.abc import AsyncIterator, Buffer
from typing import TYPE_CHECKING, Annotated, Self

import anyio
import anyio.lowlevel
import httpx
from githubkit.exception import RequestFailed
from githubkit.versions.latest.models import Artifact
from nonebot import logger
from nonebot.params import Depends
from nonebot.utils import escape_tag
from nonebot_plugin_alconna import UniMessage

from src.utils import with_semaphore

from .config import AppGitHub, plugin_config
from .data_source import WorkflowID
from .depends import Repository

if TYPE_CHECKING:
    from githubkit import AppAuthStrategy, AppInstallationAuthStrategy, GitHub
    from githubkit.versions.latest.models import Workflow, WorkflowRun


async def download_artifact(
    client: httpx.AsyncClient,
    artifact: Artifact,
    save_path: anyio.Path,
    concurrency_limit: int = plugin_config.download.concurrency_limit,
) -> None:
    chunk_send, chunk_recv = anyio.create_memory_object_stream[tuple[int, Buffer]]()
    chunk_size = plugin_config.download.chunk_size
    total_size = artifact.size_in_bytes
    total_chunks = (total_size + chunk_size - 1) // chunk_size
    max_attempts = 5

    def render_progress_log(chunk_count: int, current_time: float) -> str:
        progress_percentage = chunk_count / total_chunks * 100
        time_elapsed = current_time - time_start
        avg_speed = chunk_count * chunk_size / time_elapsed if time_elapsed > 0 else 0
        remaining_bytes = total_size - chunk_count * chunk_size
        time_remaining = remaining_bytes / avg_speed if avg_speed > 0 else float("inf")
        return (
            f"<le>{escape_tag(artifact.name)}</>: "
            f"Wrote chunk <c>{chunk_count}</>/<c>{total_chunks}</>"
            f" (<g>{progress_percentage:.2f}</>%)"
            f" | avg: <c>{avg_speed / (1024 * 1024):.2f}</> MB/s"
            f" | eta: <c>{time_remaining:.2f}</> seconds"
        )

    async def file_writer(file: anyio.AsyncFile) -> None:
        await file.truncate(total_size)  # pre-allocate file size

        chunk_count = 0
        async for start, chunk in chunk_recv:
            await file.seek(start)
            await file.write(chunk)
            chunk_count += 1
            if chunk_count % 10 == 0 or chunk_count == total_chunks:
                logger.opt(colors=True).debug(
                    render_progress_log(chunk_count, anyio.current_time())
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
        for attempt in range(1, max_attempts + 1):
            try:
                buffer = await request_chunk(chunk_range)
            except Exception as e:
                logger.opt(exception=not isinstance(e, httpx.HTTPError)).warning(
                    f"{artifact.name}: Error downloading chunk:"
                    f" seq={chunk_seq}, range={chunk_range}"
                    f" (attempt {attempt}/{max_attempts})"
                    f" - {e!r}"
                )
                excs.append(e)
                if attempt == max_attempts:
                    raise ExceptionGroup(
                        f"Failed to download chunk seq={chunk_seq}"
                        f" after {max_attempts} attempts",
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

    time_start = anyio.current_time()
    async with await save_path.open("wb") as file, anyio.create_task_group() as tg:
        tg.start_soon(file_writer, file)
        tg.start_soon(fetch_chunks)

    time_end = anyio.current_time()
    time_elapsed = time_end - time_start
    speed_mb = total_size / time_elapsed / (1024 * 1024)

    logger.info(f"{artifact.name}: Download completed in {time_elapsed:.2f} seconds")
    logger.info(f"{artifact.name}: Average speed: {speed_mb:.2f} MB/s")

    if artifact.digest and artifact.digest.startswith("sha256:"):
        sha = hashlib.sha256()
        async with await save_path.open("rb") as f:
            while chunk := await f.read(10 * 1024 * 1024):  # read in 10 MB chunks
                sha.update(chunk)
        if sha.hexdigest() != artifact.digest.removeprefix("sha256:"):
            await save_path.unlink()
            raise ValueError("Downloaded artifact digest does not match expected value")


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

    @contextlib.asynccontextmanager
    async def begin(self) -> AsyncIterator[Self]:
        async with self.github:
            yield self

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
        save_dir: anyio.Path,
    ) -> dict[str, anyio.Path]:
        saved: dict[str, anyio.Path] = {}

        async def download(artifact: Artifact) -> None:
            save_path = save_dir / f"{artifact.name}.zip"
            try:
                await download_artifact(client, artifact, save_path)
                saved[artifact.name] = save_path
            except Exception:
                logger.exception(f"Failed to download artifact {artifact.name}")

        await save_dir.mkdir(parents=True, exist_ok=True)
        async with (
            self.github.get_async_client() as client,
            anyio.create_task_group() as tg,
        ):
            for artifact in artifacts:
                tg.start_soon(download, artifact)

        return saved


async def _artifact_helper(
    app_github: AppGitHub,
    repository: Repository,
) -> AsyncIterator[ArtifactHelper]:
    owner, repo = repository

    try:
        helper = await ArtifactHelper.from_owner_repo(app_github, owner, repo)
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

    async with helper.begin():
        yield helper


Helper = Annotated[ArtifactHelper, Depends(_artifact_helper)]


async def _requested_artifacts(
    helper: Helper,
    workflow_id: WorkflowID | None = None,
) -> list[Artifact]:
    try:
        run = await helper.fetch_latest_run(workflow_id)
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
