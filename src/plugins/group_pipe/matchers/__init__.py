import contextlib

from nonebot import get_plugin, require

from . import pipe as pipe

if get_plugin("group_pipe:onebot11"):
    require("group_pipe:onebot11")
    with contextlib.suppress(ImportError, RuntimeError):
        from . import forward as forward
