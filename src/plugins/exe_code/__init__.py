from io import BytesIO
from typing import Annotated

from nonebot import on_startswith, require
from nonebot.adapters import Bot, Event
from nonebot.log import logger
from nonebot.matcher import Matcher
from nonebot.plugin import PluginMetadata
from PIL.Image import open as Image_open

require("nonebot_plugin_alconna")
require("nonebot_plugin_userinfo")
from nonebot_plugin_alconna.uniseg import Image, Reply, UniMessage, UniMsg, image_fetch
from nonebot_plugin_userinfo import EventUserInfo, UserInfo

from .code_context import Context
from .depends import EXECODE_ENABLED, EventImage, EventReplyMessage, ExtractCode

__plugin_meta__ = PluginMetadata(
    name="exe_code",
    description="在对话中执行 Python 代码",
    usage="code {Your code here...}",
    supported_adapters={
        "~onebot.v11",
        "~console",
        # "~satori",
    },
)


code_exec = on_startswith("code", rule=EXECODE_ENABLED)
code_getcode = on_startswith("getcqcode", rule=EXECODE_ENABLED)
code_getmid = on_startswith("getmid", rule=EXECODE_ENABLED)
code_getimg = on_startswith("getimg", rule=EXECODE_ENABLED)


@code_exec.handle()
async def _(
    bot: Bot,
    event: Event,
    code: Annotated[str, ExtractCode()],
    uinfo: Annotated[UserInfo, EventUserInfo()],
):
    try:
        await Context.get_context(event).execute(bot, event, code)
    except Exception as e:
        text = f"用户{uinfo.user_name}({uinfo.user_id}) 执行代码时发生错误: {e}"
        logger.opt(exception=True).warning(text)
        await UniMessage.text(f"执行失败: {e!r}").send()


@code_getcode.handle()
async def _(
    event: Event,
    msg: UniMsg,
    reply: Annotated[UniMessage, EventReplyMessage()],
):
    ctx = Context.get_context(event)
    ctx.set_gev(event)

    if msg.has(Reply):
        message = await reply.export()
        ctx.set_gem(message)
        ctx.set_gurl(reply)
    else:
        message = await msg.export()

    await UniMessage.text(str(message)).send()


@code_getmid.handle()
async def _(event: Event, msg: UniMsg):
    ctx = Context.get_context(event)
    ctx.set_gev(event)
    if msg.has(Reply):
        reply = msg[Reply, 0]
        message = type(event.get_message())(reply.msg or "")
        ctx.set_gem(message)
        ctx.set_gurl(await UniMessage.generate(message=message))
        await UniMessage.text(reply.id).send()


@code_getimg.handle()
async def _(
    bot: Bot,
    event: Event,
    matcher: Matcher,
    image: Annotated[Image, EventImage()],
):
    varname = event.get_message().extract_plain_text().removeprefix("getimg").strip()
    if (varname := varname or "img") and not varname.isidentifier():
        await matcher.finish(f"{varname} 不是一个合法的 Python 标识符")

    try:
        img_bytes = await image_fetch(event, bot, {}, image)
        if not isinstance(img_bytes, bytes):
            raise ValueError(f"获取图片数据类型错误: {type(img_bytes)!r}")
    except Exception as err:
        await matcher.finish(f"保存图片时出错: {err}")

    ctx = Context.get_context(event)
    ctx.set_value(varname, Image_open(BytesIO(img_bytes)))
    ctx.set_gev(event)
    await matcher.finish(f"图片已保存至变量 {varname}")
