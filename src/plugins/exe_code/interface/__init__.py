from nonebot.adapters import Bot

from . import adapter_api as _
from .api import API as API
from .api import api_registry
from .user_const_var import default_context as default_context
from .utils import Buffer as Buffer


def get_api_class(bot: Bot):
    bot_cls = list(api_registry.keys())
    bot_cls.remove(Bot)

    for cls in bot_cls:
        if isinstance(bot, cls):
            api_cls = api_registry[cls]
            break
    else:
        api_cls = API

    return api_cls
