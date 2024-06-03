from io import BytesIO

from nonebot import on_command, on_startswith, require
from nonebot.adapters import Bot, Event, Message
from nonebot.log import logger
from nonebot.matcher import Matcher
from nonebot.params import CommandArg
from nonebot.plugin import PluginMetadata
from nonebot.rule import Rule
from nonebot.typing import T_State
from PIL.Image import open as Image_open

require("nonebot_plugin_alconna")
require("nonebot_plugin_saa")
from nonebot_plugin_alconna.uniseg import Image, Reply, UniMessage, UniMsg, image_fetch
from nonebot_plugin_saa import extract_target

from .code_context import ContextManager
from .config import cfg

__plugin_meta__ = PluginMetadata(
    name="exe_code",
    description="在对话中执行 Python 代码",
    usage="code {Your code here...}",
    supported_adapters={
        "~onebot.v11",
        # "~satori",
    },
)


def ExeCodeEnabled():
    from nonebot_plugin_saa import (
        TargetQQGroup,
        TargetQQGroupOpenId,
        TargetQQGuildChannel,
    )

    def check(bot: Bot, event: Event):
        user_id = event.get_user_id()
        if user_id in cfg.user:
            return True

        gid = None
        target = extract_target(event,bot)
        if isinstance(target, TargetQQGroup):
            gid = target.group_id
        elif isinstance(target, TargetQQGroupOpenId):
            gid = target.group_openid
        elif isinstance(target, TargetQQGuildChannel):
            gid = target.channel_id
        else:
            return False

        return gid is not None and (str(gid) in cfg.group)

    return Rule(check)


EXECODE_ENABLED = ExeCodeEnabled()

code_exec = on_command("code", rule=EXECODE_ENABLED, aliases={"exec"}, priority=1)
code_getcode = on_startswith("getcqcode", rule=EXECODE_ENABLED)
code_getmid = on_startswith("getmid", rule=EXECODE_ENABLED)
code_getimg = on_startswith("getimg", rule=EXECODE_ENABLED)


@code_exec.handle()
async def _(
    matcher: Matcher,
    bot: Bot,
    event: Event,
    args: Message = CommandArg(),
):
    code = args.extract_plain_text().strip()
    ctx = ContextManager.get_context(event)

    try:
        await ctx.execute(bot, event, code)
    except Exception as e:
        uinfo = await bot.call_api("get_stranger_info", user_id=event.get_user_id())
        logger.opt(exception=True).warning(
            f"用户{uinfo['nickname']}({event.get_user_id()}) 执行代码时发生错误: {e}"
        )
        await matcher.finish(f"执行失败: {e!r}")


@code_getcode.handle()
async def _(event: Event, msg: UniMsg):
    ctx = ContextManager.get_context(event)
    ctx.set_gev(event)

    message = await msg.export()
    if msg.has(Reply):
        reply = type(message)(msg[Reply][0].msg)
        ctx.set_gem(reply)
        message = reply or ""
        ctx.set_gurl(await UniMessage.generate(message=reply))

    await UniMessage.text(str(message)).send()


@code_getmid.handle()
async def _(event: Event, msg: UniMsg):
    ctx = ContextManager.get_context(event)
    ctx.set_gev(event)
    if msg.has(Reply):
        reply = msg[Reply][0]
        message = type(await msg.export())(reply.msg)
        ctx.set_gem(message)
        ctx.set_gurl(await UniMessage.generate(message=message))
        await UniMessage.text(reply.id).send()


@code_getimg.handle()
async def _(matcher: Matcher, bot: Bot, event: Event, msg: UniMsg, state: T_State):
    if not msg.has(Reply):
        await matcher.finish("未引用消息")

    reply_msg = msg[Reply][0].msg
    if not isinstance(reply_msg, Message):
        await matcher.finish("无法获取引用图片")

    reply = await UniMessage.generate(message=reply_msg)
    if not reply.has(Image):
        await matcher.finish("引用消息中没有图片")

    varname = msg.extract_plain_text().removeprefix("getimg").strip() or "img"
    if not varname.isidentifier():
        await matcher.finish(f"{varname} 不是一个合法的 Python 标识符")

    try:
        img = await image_fetch(event, bot, state, reply[Image, 0])
        if not isinstance(img, bytes):
            raise ValueError(f"获取图片数据类型错误: {type(img)!r}")
    except Exception as err:
        await matcher.finish(f"保存图片时出错: {err}")

    ctx = ContextManager.get_context(event)
    ctx.set_value(varname, Image_open(BytesIO(img)))
    ctx.set_gev(event)
    ctx.set_gurl(reply)
    ctx.set_gem(reply_msg)
    await matcher.finish(f"图片已保存至变量 {varname}")
