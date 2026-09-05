from arclet.alconna import Alconna, Args, CommandMeta, Option, Subcommand
from nonebot.permission import SUPERUSER
from nonebot_plugin_alconna import on_alconna


def _endpoint_options() -> tuple[Option, ...]:
    return (
        Option(
            "--protocol|-p",
            Args["protocol#Endpoint 协议", str],
            help_text="openai-completions、openai-responses 或 anthropic-messages",
        ),
        Option(
            "--base-url|-u",
            Args["base_url#Endpoint Base URL", str],
            help_text="Provider API Base URL",
        ),
        Option(
            "--timeout",
            Args["timeout_seconds#请求超时秒数", float],
            help_text="请求超时秒数",
        ),
        Option(
            "--max-retries",
            Args["max_retries#最大重试次数", int],
            help_text="SDK 最大重试次数",
        ),
    )


def _model_options() -> tuple[Option, ...]:
    return (
        Option(
            "--endpoint|-e",
            Args["endpoint#Endpoint 别名", str],
            help_text="模型使用的 Endpoint",
        ),
        Option(
            "--model-id|-m",
            Args["model_id#Provider 模型 ID", str],
            help_text="Provider 侧的模型 ID",
        ),
        Option(
            "--max-concurrent|-c",
            Args["max_concurrent#最大并发数", int],
            help_text="模型最大并发请求数",
        ),
        Option(
            "--default-max-output-tokens",
            Args["default_max_output_tokens#默认最大输出 token", str],
            help_text="正整数；使用“空”清空（Anthropic Messages 必填）",
        ),
        Option(
            "--tools",
            Args["tools#true/false", bool],
            help_text="是否支持工具调用",
        ),
        Option(
            "--vision",
            Args["vision#true/false", bool],
            help_text="是否支持图片输入",
        ),
        Option(
            "--temperature",
            Args["temperature#true/false", bool],
            help_text="是否支持 temperature 参数",
        ),
        Option(
            "--reasoning",
            Args["reasoning_efforts#reasoning effort 列表", str],
            help_text="按能力从低到高用逗号分隔，使用“空”清空",
        ),
        Option(
            "--structured",
            Args["structured_output_modes#structured output mode 列表", str],
            help_text="按降级顺序用逗号分隔，使用“空”清空",
        ),
        Option(
            "--parallel-tools",
            Args["parallel_tool_calls#true/false", bool],
            help_text="是否支持并行工具调用",
        ),
        Option(
            "--anthropic-thinking",
            Args["anthropic_thinking#thinking 设置", str],
            help_text="none、disabled、adaptive 或 enabled",
        ),
        Option(
            "--anthropic-thinking-budget",
            Args["anthropic_thinking_budget#thinking token 预算", int],
            help_text="enabled thinking 的固定 token 预算",
        ),
        Option(
            "--selectable",
            Args["selectable#true/false", bool],
            help_text="是否允许作为全局活动模型",
        ),
    )


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
                    *_endpoint_options(),
                    help_text="通过私聊向导添加 Endpoint",
                ),
                Subcommand(
                    "edit",
                    Args["alias#Endpoint 别名", str],
                    *_endpoint_options(),
                    help_text="通过私聊向导编辑 Endpoint",
                ),
                Subcommand(
                    "remove",
                    Args["alias#Endpoint 别名", str],
                    help_text="删除未被模型引用的 Endpoint",
                ),
                help_text="管理多协议 LLM Endpoint",
            ),
            Subcommand(
                "model",
                Subcommand(
                    "add",
                    Args["alias#模型别名", str],
                    *_model_options(),
                    help_text="添加模型；未提供的配置项通过私聊询问",
                ),
                Subcommand(
                    "edit",
                    Args["alias#模型别名", str],
                    *_model_options(),
                    help_text="编辑模型；未提供的配置项通过私聊询问",
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
                "llm config model <add|edit> <模型别名> [配置选项]\n"
                "llm config model remove <模型别名>"
            ),
            example=(
                "llm status\n"
                "llm model use gpt\n"
                "llm config setup\n"
                "llm config endpoint edit local\n"
                "llm config endpoint add claude --protocol anthropic-messages\n"
                "llm config model add vision --endpoint local --model-id gpt-vision "
                "--vision true --temperature true --tools true --parallel-tools true"
            ),
            author="wyf7685",
        ),
    ),
    permission=SUPERUSER,
    use_cmd_start=True,
    block=True,
)


__all__ = ["model_admin"]
