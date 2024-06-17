from io import BytesIO
from typing import Annotated

from nonebot import on_startswith, require
from nonebot.adapters import Bot, Event, Message
from nonebot.log import logger
from nonebot.matcher import Matcher
from nonebot.plugin import PluginMetadata
from nonebot.plugin.load import inherit_supported_adapters
from PIL.Image import open as Image_open

require("nonebot_plugin_alconna")
require("nonebot_plugin_datastore")
require("nonebot_plugin_session")
require("nonebot_plugin_userinfo")
from nonebot_plugin_alconna.uniseg import Image, Reply, UniMessage, UniMsg, image_fetch
from nonebot_plugin_session import EventSession
from nonebot_plugin_userinfo import EventUserInfo, UserInfo

from .code_context import Context
from .config import Config
from .depends import (
    EXECODE_ENABLED,
    EventImage,
    EventReply,
    EventReplyMessage,
    ExtractCode,
)

__plugin_meta__ = PluginMetadata(
    name="exe_code",
    description="在对话中执行 Python 代码",
    usage="code {Your code here...}",
    type="application",
    config=Config,
    supported_adapters=inherit_supported_adapters(
        "nonebot_plugin_alconna",
        "nonebot_plugin_datastore",
        "nonebot_plugin_userinfo",
    ),
    extra={"author": "wyf7685"},
)


code_exec = on_startswith("code", rule=EXECODE_ENABLED)
code_getcode = on_startswith("getcqcode", rule=EXECODE_ENABLED)
code_getmid = on_startswith("getmid", rule=EXECODE_ENABLED)
code_getimg = on_startswith("getimg", rule=EXECODE_ENABLED)


@code_exec.handle()
async def _(
    bot: Bot,
    session: EventSession,
    code: Annotated[str, ExtractCode()],
    uinfo: Annotated[UserInfo, EventUserInfo()],
):
    try:
        await Context.execute(session, bot, code)
    except Exception as e:
        text = f"用户{uinfo.user_name}({uinfo.user_id}) 执行代码时发生错误: {e}"
        logger.opt(exception=True).warning(text)
        await UniMessage.text(f"执行失败: {e!r}").send()


@code_getcode.handle()
async def _(
    event: Event,
    session: EventSession,
    message: Annotated[Message, EventReplyMessage()],
):
    ctx = Context.get_context(session)
    ctx.set_gev(event)
    ctx.set_gem(message)
    ctx.set_gurl(await UniMessage.generate(message=message))
    await UniMessage.text(str(message)).send()


@code_getmid.handle()
async def _(
    event: Event,
    session: EventSession,
    reply: Annotated[Reply, EventReply()],
):
    ctx = Context.get_context(session)
    message = type(event.get_message())(reply.msg or "")
    ctx.set_gev(event)
    ctx.set_gem(message)
    ctx.set_gurl(await UniMessage.generate(message=message))
    await UniMessage.text(reply.id).send()


@code_getimg.handle()
async def _(
    bot: Bot,
    event: Event,
    session: EventSession,
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

    ctx = Context.get_context(session)
    ctx.set_gev(event)
    ctx.set_gurl(image)
    ctx.set_value(varname, Image_open(BytesIO(img_bytes)))
    await matcher.finish(f"图片已保存至变量 {varname}")
