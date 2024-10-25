import asyncio
import base64
import contextlib
import shutil
import sys
from pathlib import Path
from typing import Any

from nonebot import get_plugin_config
from nonebot.adapters import Bot
from nonebot.adapters.onebot.v11 import Bot as V11Bot
from nonebot.adapters.onebot.v11 import Message
from pydantic import BaseModel


class Config(BaseModel):
    fix_v11_image_share_path: Path
    fix_v11_image_file_expire: float = 60.0 * 3


config = get_plugin_config(Config)
share_path = config.fix_v11_image_share_path.resolve()
file_expire = config.fix_v11_image_file_expire

if not share_path.exists():
    share_path.mkdir(parents=True)


def safe_remove(file: Path) -> None:
    if file.exists():
        with contextlib.suppress(Exception):
            file.unlink()


def fix_file(file: str) -> str:
    if file.startswith("base64://"):
        b64 = file.removeprefix("base64://")
        tmp_file = share_path / str(hash(b64))
        tmp_file.write_bytes(base64.b64decode(b64))
        asyncio.get_event_loop().call_later(file_expire, safe_remove, tmp_file)
        return tmp_file.as_uri()

    if not file.startswith("file://"):
        return file

    if sys.platform == "win32":
        file = file.removeprefix("file:///")
    elif sys.platform == "linux":
        file = file.removeprefix("file://")
    else:
        return file

    tmp_file = share_path / str(hash(file))
    shutil.copyfile(file, tmp_file)
    asyncio.get_event_loop().call_later(file_expire, safe_remove, tmp_file)
    return tmp_file.as_uri()


def fix_message(message: Message | list[dict[str, Any]]) -> Message | list[dict]:
    for seg in message:
        if isinstance(seg, dict):
            if seg["type"] == "image":
                seg["data"]["file"] = fix_file(seg["data"]["file"])
        elif seg.type == "image":
            seg.data["file"] = fix_file(seg.data["file"])
    return message


@Bot.on_calling_api
async def _(bot: Bot, api: str, data: dict[str, Any]) -> None:
    if not isinstance(bot, V11Bot):
        return

    if api in {"send_msg", "send_private_msg", "send_group_msg"}:
        with contextlib.suppress(Exception):
            data["message"] = fix_message(Message(data["message"]))

    elif api in {"send_private_forward_msg", "send_group_forward_msg"}:
        for item in data["messages"]:
            item["content"] = fix_message(item["content"])
