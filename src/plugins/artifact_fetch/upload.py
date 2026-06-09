from pathlib import Path

import anyio
from nonebot_plugin_alconna import Target, UniMessage

from src.plugins.upload_cos import upload_cos

ARTIFACT_TTL_SECS = 60 * 60 * 24 * 7  # 7 days


async def upload_artifacts(
    saved: dict[str, Path],
    target: Target | None,
    reply_to: bool | None = None,
) -> None:
    async def upload(name: str, file: Path) -> None:
        url = await upload_cos(file, key=f"artifacts/{name}", ttl=ARTIFACT_TTL_SECS)
        urls[name] = url

    urls: dict[str, str] = {}
    async with anyio.create_task_group() as tg:
        for name, file in saved.items():
            tg.start_soon(upload, name, file)

    await UniMessage.text(
        "Artifact 下载完成:\n"
        + "\n\n".join(f"{name}:\n{url}" for name, url in urls.items())
    ).send(target, reply_to=reply_to)
