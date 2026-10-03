from collections.abc import Generator

from nonebot import on_type
from nonebot.adapters.milky.event import GroupMessageReactionEvent
from nonebot_plugin_alconna import CustomNode, UniMessage

from ..run_logs import (
    get_run_log,
    has_run_log,
    run_log_cache_key,
    safe_render_run_log,
)

EYES = "289"
_MAX_FORWARD_NODE_CHARS = 16_000


def _reaction_cache_key(event: GroupMessageReactionEvent) -> str:
    group_id = str(event.data.group_id)
    message_id = f"{event.data.message_seq}@group:{group_id}"
    return run_log_cache_key(
        bot_id=str(event.self_id),
        adapter_name="Milky",
        scene_type="group",
        scene_id=group_id,
        message_id=message_id,
    )


async def _reaction_rule(event: GroupMessageReactionEvent) -> bool:
    if (
        event.data.face_id != EYES
        or not event.data.is_add
        or str(event.data.user_id) == str(event.self_id)
    ):
        return False
    return await has_run_log(_reaction_cache_key(event))


def _split_log_node(node: CustomNode) -> Generator[CustomNode]:
    if not isinstance(node.content, str):
        yield node
        return

    content = node.content
    while len(content) > _MAX_FORWARD_NODE_CHARS:
        split_at = content.rfind("\n", 1, _MAX_FORWARD_NODE_CHARS)
        if split_at <= 0:
            split_at = _MAX_FORWARD_NODE_CHARS
        yield CustomNode(uid=node.uid, name=node.name, content=content[:split_at])
        content = content[split_at:]
    if content:
        yield CustomNode(uid=node.uid, name=node.name, content=content)


reaction_matcher = on_type(
    GroupMessageReactionEvent,
    rule=_reaction_rule,
    priority=10,
)


@reaction_matcher.handle()
async def handle_run_log_reaction(event: GroupMessageReactionEvent) -> None:
    log_text = await get_run_log(_reaction_cache_key(event))
    if log_text is None:
        return

    image = await safe_render_run_log(log_text)
    content = UniMessage.image(raw=image) if image is not None else log_text
    node = CustomNode(
        uid=event.get_user_id(),
        name="ZSSM run logs",
        content=content,
    )
    await UniMessage.reference(*_split_log_node(node)).send()


__all__ = ["handle_run_log_reaction", "reaction_matcher"]
