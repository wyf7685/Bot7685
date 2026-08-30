from collections.abc import Sequence

import anyio
from nonebot import logger
from nonebot_plugin_alconna import Target, UniMessage

from src.plugins.upload_cos import upload_cos

from .data_source import DownloadedArtifact

ARTIFACT_TTL_SECS = 60 * 60 * 24 * 7  # 7 days


async def upload_artifacts(
    saved: Sequence[DownloadedArtifact],
    target: Target | None,
    reply_to: bool | None = None,
    *,
    key_prefix: str,
) -> None:
    uploaded: dict[int, str] = {}
    failed: dict[int, str] = {}

    async def upload(artifact: DownloadedArtifact) -> None:
        try:
            url = await upload_cos(
                artifact.path,
                key=f"{key_prefix}/{artifact.artifact_id}.zip",
                ttl=ARTIFACT_TTL_SECS,
            )
        except Exception:
            logger.exception(f"Failed to upload artifact {artifact.name}")
            failed[artifact.artifact_id] = artifact.name
        else:
            uploaded[artifact.artifact_id] = url

    async with anyio.create_task_group() as tg:
        for artifact in saved:
            tg.start_soon(upload, artifact)

    lines = [
        f"{artifact.name}:\n{uploaded[artifact.artifact_id]}"
        for artifact in saved
        if artifact.artifact_id in uploaded
    ]
    if failed:
        lines.append("上传失败:\n" + "\n".join(f"- {name}" for name in failed.values()))
    if not lines:
        lines.append("上传失败: " + "、".join(failed.values()))

    await UniMessage.text("Artifact 下载完成:\n" + "\n\n".join(lines)).send(
        target, reply_to=reply_to
    )
