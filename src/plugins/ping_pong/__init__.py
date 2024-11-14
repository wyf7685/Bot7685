import pathlib
import secrets
from typing import Any

from nonebot import require
from nonebot.plugin import PluginMetadata, inherit_supported_adapters

require("nonebot_plugin_alconna")
from nonebot_plugin_alconna import (
    Alconna,
    Args,
    CommandMeta,
    Option,
    UniMessage,
    on_alconna,
)
from nonebot_plugin_alconna.builtins.extensions.telegram import TelegramSlashExtension

__plugin_meta__ = PluginMetadata(
    name="ping",
    description="ping-pong!",
    usage="发送 /ping",
    type="application",
    supported_adapters=inherit_supported_adapters("nonebot_plugin_alconna"),
)

"""
用法: ping [-t] [-a] [-n count] [-l size] [-f] [-i TTL] [-v TOS]
            [-r count] [-s count] [[-j host-list] | [-k host-list]]
            [-w timeout] [-R] [-S srcaddr] [-c compartment] [-p]
            [-4] [-6] target_name

选项:
    -t             Ping 指定的主机，直到停止。
                   若要查看统计信息并继续操作，请键入 Ctrl+Break；
                   若要停止，请键入 Ctrl+C。
    -a             将地址解析为主机名。
    -n count       要发送的回显请求数。
    -l size        发送缓冲区大小。
    -f             在数据包中设置“不分段”标记(仅适用于 IPv4)。
    -i TTL         生存时间。
    -v TOS         服务类型(仅适用于 IPv4。该设置已被弃用，
                   对 IP 标头中的服务类型字段没有任何
                   影响)。
    -r count       记录计数跃点的路由(仅适用于 IPv4)。
    -s count       计数跃点的时间戳(仅适用于 IPv4)。
    -j host-list   与主机列表一起使用的松散源路由(仅适用于 IPv4)。
    -k host-list    与主机列表一起使用的严格源路由(仅适用于 IPv4)。
    -w timeout     等待每次回复的超时时间(毫秒)。
    -R             同样使用路由标头测试反向路由(仅适用于 IPv6)。
                   根据 RFC 5095，已弃用此路由标头。
                   如果使用此标头，某些系统可能丢弃
                   回显请求。
    -S srcaddr     要使用的源地址。
    -c compartment 路由隔离舱标识符。
    -p             Ping Hyper-V 网络虚拟化提供程序地址。
    -4             强制使用 IPv4。
    -6             强制使用 IPv6。
"""

alc = Alconna(
    "ping",
    Option(
        "-t",
        help_text=(
            "Ping 指定的主机，直到停止。"
            " 若要查看统计信息并继续操作，请键入 Ctrl+Break；"
            " 若要停止，请键入 Ctrl+C。"
        ),
    ),
    Option("-a", help_text="将地址解析为主机名。"),
    Option("-n", Args["count", int], help_text="要发送的回显请求数。"),
    Option("-l", Args["size", int], help_text="发送缓冲区大小。"),
    Option("-f", help_text="在数据包中设置“不分段”标记(仅适用于 IPv4)。"),
    Option("-i", Args["TTL", int], help_text="生存时间。"),
    Option(
        "-v",
        Args["TOS", str],
        help_text=(
            "服务类型(仅适用于 IPv4。该设置已被弃用，"
            "对 IP 标头中的服务类型字段没有任何影响)。"
        ),
    ),
    Option("-r", Args["count", int], help_text="记录计数跃点的路由(仅适用于 IPv4)。"),
    Option("-s", Args["count", int], help_text="计数跃点的时间戳(仅适用于 IPv4)。"),
    Option(
        "-j",
        Args["host-list", str],
        help_text="与主机列表一起使用的松散源路由(仅适用于 IPv4)。",
    ),
    Option(
        "-k",
        Args["host-list", str],
        help_text="与主机列表一起使用的严格源路由(仅适用于 IPv4)。",
    ),
    Option("-w", Args["timeout", int], help_text="等待每次回复的超时时间(毫秒)。"),
    Option(
        "-R",
        help_text=(
            "同样使用路由标头测试反向路由(仅适用于 IPv6)。"
            "根据 RFC 5095，已弃用此路由标头。"
            "如果使用此标头，某些系统可能丢弃回显请求。"
        ),
    ),
    Option("-S", Args["srcaddr", str], help_text="要使用的源地址。"),
    Option("-c", Args["compartment", str], help_text="路由隔离舱标识符。"),
    Option("-p", help_text="Ping Hyper-V 网络虚拟化提供程序地址。"),
    Option("-4", help_text="强制使用 IPv4。"),
    Option("-6", help_text="强制使用 IPv6。"),
    Args["target_name?", Any],
    meta=CommandMeta(
        description="Command: ping",
        usage="ping [-t] [-a] [-n count] [-l size] [-f] [-i TTL] [-v TOS] "
        "[-r count] [-s count] [[-j host-list] | [-k host-list]] "
        "[-w timeout] [-R] [-S srcaddr] [-c compartment] [-p] "
        "[-4] [-6] target_name",
        example="ping -n 4 -w 1000 www.baidu.com",
    ),
)
ping = on_alconna(
    alc,
    priority=10,
    use_cmd_start=True,
    extensions=[TelegramSlashExtension()],
)
root = pathlib.Path(__file__).resolve().parent / "images"
images = list(root.glob("*.jpg"))


@ping.handle()
async def _() -> None:
    await (
        UniMessage.text("pong")
        .image(raw=secrets.choice(images).read_bytes())
        .send(reply_to=True)
    )
