from nonebot import on_startswith
from nonebot.adapters.onebot.v11 import Bot, MessageEvent, MessageSegment

from .constant import image_fps, image_text, random
from .router import setup_router

url = setup_router()


@on_startswith(("抽黍泡泡", "黍泡泡")).handle()
async def _(bot: Bot, event: MessageEvent):
    fp = random.choice(image_fps)

    img = MessageSegment.image(file=str(url.with_query({"key": fp.name})))
    img.data["summary"] = image_text.get(fp.stem, "黍泡泡")
    msg = MessageSegment.reply(event.message_id) + img

    await bot.send(event, msg)
