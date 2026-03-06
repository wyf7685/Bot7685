from typing import Any, cast, final, override

import anyio
from nonebot import logger
from nonebot.adapters.milky import Bot, Event
from nonebot.adapters.milky.event import FriendMessageEvent, GroupMessageEvent
from nonebot.exception import NetworkError
from nonebot_plugin_alconna import Target

from ..base import UploadProvider


async def extract_extra(
    bot: Bot,
    event: FriendMessageEvent | GroupMessageEvent,
    target_folder: str | None = None,
) -> dict[str, Any]:
    if isinstance(event, FriendMessageEvent):
        return {}

    group_id = event.data.peer_id

    root_files = await bot.get_group_files(group_id=group_id)
    if target_folder is None:
        return {}

    gen = (f.folder_id for f in root_files.folders if f.folder_name == target_folder)
    if (target_folder_id := next(gen, None)) is None:
        target_folder_id = await bot.create_group_folder(
            group_id=group_id, folder_name=target_folder
        )

    return {"folder_id": target_folder_id}


@final
class MilkyUploadProvider(UploadProvider[Bot, Event]):
    extract_extra = extract_extra

    @override
    @classmethod
    async def verify(cls, target: Target) -> bool:
        try:
            bot = await target.select()
        except Exception:
            return False

        return isinstance(bot, Bot)

    @override
    async def do_upload(
        self,
        file: anyio.Path,
        name: str,
        target: Target,
        extra: dict[str, Any],
    ) -> None:
        bot = cast("Bot", await target.select())

        try:
            if target.private:
                await bot.upload_private_file(
                    user_id=int(target.id),
                    raw=await file.read_bytes(),
                    file_name=name,
                )
            else:
                folder_id = extra.get("folder_id")
                await bot.upload_group_file(
                    group_id=int(target.id),
                    parent_folder_id=folder_id,
                    raw=await file.read_bytes(),
                    file_name=name,
                )
        except NetworkError as exc:
            if "ReadTimeout" in str(exc):
                logger.warning(
                    f"Got ReadTimeout while uploading artifact {name}, assuming success"
                )
            else:
                raise
