import functools
import shutil
import uuid

import anyio
import anyio.to_thread
from nonebot import logger
from nonebot.adapters.milky import Bot as MilkyBot
from nonebot.adapters.milky.event import GroupMessageEvent
from nonebot.adapters.milky.model.api import FilesInfo
from nonebot.exception import NetworkError
from nonebot_plugin_alconna import (
    Alconna,
    Args,
    Option,
    Subcommand,
    UniMessage,
    on_alconna,
)
from nonebot_plugin_localstore import get_plugin_cache_dir

from .artifact_helper import Helper

CACHE_DIR = anyio.Path(get_plugin_cache_dir())

alc = Alconna(
    "artifact",
    Subcommand(
        "fetch",
        Option("--owner|-o", Args["owner", str]),
        Option("--repo|-r", Args["repo", str]),
        Option("--workflow-id|-w", Args["workflow_id?", int | str]),
        Option("--target-folder", Args["target_folder?", str]),
    ),
    Subcommand(
        "subscribe",
        # TODO: ...
    ),
)
matcher = on_alconna(alc)


async def get_target_folder(
    bot: MilkyBot,
    group_id: int,
    target_folder: str | None = None,
) -> tuple[str | None, FilesInfo]:
    root_files = await bot.get_group_files(group_id=group_id)
    if target_folder is None:
        return None, root_files

    gen = (f.folder_id for f in root_files.folders if f.folder_name == target_folder)
    if (target_folder_id := next(gen, None)) is None:
        target_folder_id = await bot.create_group_folder(
            group_id=group_id, folder_name=target_folder
        )

    return target_folder_id, await bot.get_group_files(
        group_id=group_id, parent_folder_id=target_folder_id
    )


@matcher.assign("~fetch")
async def assign_fetch(
    bot: MilkyBot,
    event: GroupMessageEvent,
    helper: Helper,
    workflow_id: int | str | None = None,
    target_folder: str | None = None,
) -> None:
    run = await helper.fetch_latest_run(workflow_id)
    artifacts = await helper.fetch_artifacts(run.id)
    if not artifacts:
        await UniMessage.text("未找到最新工作流运行的任何 artifact").finish(
            reply_to=True
        )
    artifact_names = {f"{artifact.name}.zip" for artifact in artifacts}

    target_folder_id, target_folder_info = await get_target_folder(
        bot, event.data.peer_id, target_folder
    )
    folder_file_names = {f.file_name for f in target_folder_info.files}
    if artifact_names.issubset(folder_file_names):
        await UniMessage.text(
            "所有 artifact 已存在于目标文件夹中，无需重复上传。"
        ).finish(reply_to=True)
    artifacts = [a for a in artifacts if f"{a.name}.zip" not in folder_file_names]

    save_dir = CACHE_DIR / uuid.uuid4().hex
    await save_dir.mkdir(parents=True, exist_ok=True)
    saved = await helper.download_artifacts(*artifacts, save_dir=save_dir)

    if not saved:
        await UniMessage.text("未能成功下载任何 artifact").finish(reply_to=True)

    async def upload_file(name: str, path: anyio.Path) -> None:
        if not await path.exists():
            logger.warning(
                f"Artifact {name} was not downloaded successfully, skipping upload"
            )
            return

        try:
            await bot.upload_group_file(
                group_id=event.data.peer_id,
                parent_folder_id=target_folder_id,
                raw=await path.read_bytes(),
                file_name=path.name,
            )
        except NetworkError as exc:
            if "ReadTimeout" in str(exc):
                logger.warning(
                    f"Got ReadTimeout while uploading artifact {name}, assuming success"
                )
        except Exception as exc:
            logger.exception(f"Failed to upload artifact {name} to group folder")
            await UniMessage.text(f"上传 artifact {name} 失败\n{exc!r}").finish(
                reply_to=True
            )

    try:
        async with anyio.create_task_group() as tg:
            for name, path in saved.items():
                tg.start_soon(upload_file, name, path)
    finally:
        await anyio.to_thread.run_sync(
            functools.partial(shutil.rmtree, save_dir, ignore_errors=True)
        )
