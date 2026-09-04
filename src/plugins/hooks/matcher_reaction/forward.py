import asyncio
from collections.abc import Generator, Iterable

from nonebot import on_type, require
from nonebot.adapters.milky.event import GroupMessageReactionEvent
from nonebot_plugin_alconna import CustomNode, UniMessage

require("nonebot_plugin_htmlrender")
from . import store
from .render import safe_render_traceback

EYES = "289"
CONTENT_MAX_LENGTH = 16_000


def split_nodes(nodes: Iterable[CustomNode]) -> Generator[CustomNode]:
    for node in nodes:
        if not isinstance(node.content, str):
            yield node
            continue

        content = node.content
        if len(content) <= CONTENT_MAX_LENGTH:
            yield node
            continue

        while content:
            if len(content) <= CONTENT_MAX_LENGTH:
                yield CustomNode(uid=node.uid, name=node.name, content=content)
                break

            # 优先在换行处断开; 首字符即换行时 rfind 会返回 0, 直接切走会
            # 产生空分片并导致死循环, 因此下界固定为 1
            split_pos = content.rfind("\n", 1, CONTENT_MAX_LENGTH)
            if split_pos <= 0:
                split_pos = CONTENT_MAX_LENGTH
            yield CustomNode(uid=node.uid, name=node.name, content=content[:split_pos])
            content = content[split_pos:]


def _reaction_message_id(event: GroupMessageReactionEvent) -> str:
    return f"{event.data.message_seq}@group:{event.data.group_id}"


async def _reaction_rule(event: GroupMessageReactionEvent) -> bool:
    if event.data.face_id != EYES or not event.data.is_add:
        return False
    return await store.exists(_reaction_message_id(event))


reaction_matcher = on_type(
    GroupMessageReactionEvent,
    rule=_reaction_rule,
    priority=10,
)


@reaction_matcher.handle()
async def handle_reaction(event: GroupMessageReactionEvent) -> None:
    records = await store.get(_reaction_message_id(event))
    if not records:
        return

    # 渲染失败时回退到纯文本节点, 保证 traceback 始终可读
    images = await asyncio.gather(*map(safe_render_traceback, records))
    uid = event.get_user_id()

    nodes = [
        CustomNode(
            uid=uid,
            name=f"{record.matcher} at {record.source}",
            content=(
                UniMessage.image(raw=image)
                if image is not None
                else (
                    f"Exception: {record.exception}\n"
                    f"Matcher: {record.matcher}\n"
                    f"Source: {record.source}\n"
                    f"\n\n{record.traceback}"
                )
            ),
        )
        for record, image in zip(records, images, strict=True)
    ]

    await UniMessage.reference(*split_nodes(nodes)).send()
