import json
from pathlib import Path
from random import Random
from base64 import b64encode
from nonebot import on_startswith
from nonebot.adapters.onebot.v11 import Bot, GroupMessageEvent


random = Random()
# 图源: Bilibili@鱼烤箱
root = Path(__file__).parent.resolve()
image_fps = list((root / "images").iterdir())
image_text = json.loads((root / "text.json").read_text(encoding="utf-8"))


@on_startswith(("抽黍泡泡", "黍泡泡")).handle()
async def _(bot: Bot, event: GroupMessageEvent):
    fp = random.choice(image_fps)
    await bot.call_api(
        "send_group_msg",
        group_id=event.group_id,
        message=[
            {
                "type": "image",
                "data": {
                    "file": "base64://" + b64encode(fp.read_bytes()).decode(),
                    "summary": image_text[fp.name.split(".")[0]],
                },
            }
        ],
    )
