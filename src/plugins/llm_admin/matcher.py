from arclet.alconna import Alconna, Args, CommandMeta, Subcommand
from nonebot.permission import SUPERUSER
from nonebot_plugin_alconna import on_alconna

model_admin = on_alconna(
    Alconna(
        "llm",
        Subcommand("status", help_text="查看完整 LLM 配置状态"),
        Subcommand(
            "model",
            Subcommand("list", help_text="列出模型及当前活动模型"),
            Subcommand(
                "use",
                Args["alias#模型别名", str],
                help_text="切换全局活动模型",
            ),
            help_text="查看或切换活动模型",
        ),
        Subcommand(
            "config",
            Subcommand("setup", help_text="通过私聊向导创建首次配置"),
            Subcommand("reset", help_text="删除全部 LLM 配置"),
            Subcommand(
                "endpoint",
                Subcommand("list", help_text="列出所有 Endpoint"),
                Subcommand(
                    "add",
                    Args["alias#Endpoint 别名", str],
                    help_text="通过私聊向导添加 Endpoint",
                ),
                Subcommand(
                    "edit",
                    Args["alias#Endpoint 别名", str],
                    help_text="通过私聊向导编辑 Endpoint",
                ),
                Subcommand(
                    "remove",
                    Args["alias#Endpoint 别名", str],
                    help_text="删除未被模型引用的 Endpoint",
                ),
                help_text="管理 OpenAI 兼容 Endpoint",
            ),
            Subcommand(
                "model",
                Subcommand(
                    "add",
                    Args["alias#模型别名", str],
                    help_text="通过私聊向导添加模型",
                ),
                Subcommand(
                    "edit",
                    Args["alias#模型别名", str],
                    help_text="通过私聊向导编辑模型",
                ),
                Subcommand(
                    "remove",
                    Args["alias#模型别名", str],
                    help_text="删除非活动模型",
                ),
                help_text="管理模型及能力配置",
            ),
            help_text="管理持久化 LLM 配置，仅 Superuser 可用",
        ),
        meta=CommandMeta(
            description="管理 Bot 的 LLM Endpoint、模型能力和活动模型",
            usage=(
                "llm status\n"
                "llm model <list|use> [模型别名]\n"
                "llm config <setup|reset>\n"
                "llm config endpoint <list|add|edit|remove> [Endpoint 别名]\n"
                "llm config model <add|edit|remove> [模型别名]"
            ),
            example=(
                "llm status\n"
                "llm model use gpt\n"
                "llm config setup\n"
                "llm config endpoint edit local\n"
                "llm config model add vision"
            ),
            author="wyf7685",
        ),
    ),
    permission=SUPERUSER,
    use_cmd_start=True,
    block=True,
)


__all__ = ["model_admin"]
