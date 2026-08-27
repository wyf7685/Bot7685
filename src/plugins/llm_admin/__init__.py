from nonebot.plugin import PluginMetadata, inherit_supported_adapters

__plugin_meta__ = PluginMetadata(
    name="LLM Model Manager",
    description="通过私聊向导管理 Bot 全局 LLM 配置与活动模型",
    usage=(
        "llm status\n"
        "llm model list|use <alias>\n"
        "llm config setup|reset\n"
        "llm config endpoint list|add|edit|remove\n"
        "llm config model add|edit|remove"
    ),
    type="application",
    supported_adapters=inherit_supported_adapters("nonebot_plugin_alconna"),
    extra={"author": "wyf7685"},
)

from . import endpoints as _endpoints
from . import models as _models
from . import setup as _setup
from . import status as _status
from .matcher import model_admin as model_admin

_HANDLER_MODULES = (_endpoints, _models, _setup, _status)

__all__ = ["model_admin"]
