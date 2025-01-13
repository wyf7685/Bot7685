import itertools

from nonebot.adapters.onebot.v11 import MessageEvent
from nonebot.message import event_preprocessor


@event_preprocessor
async def _(event: MessageEvent) -> None:
    for seg in itertools.chain(event.message, event.original_message):
        if seg.type == "image":
            url: str = seg.data.get("url", "")
            if "https://multimedia.nt.qq.com.cn" in url:
                seg.data["url"] = url.replace("https://multimedia", "http://multimedia")
