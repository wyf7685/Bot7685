import asyncio
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass, field

from nonebot.adapters import Bot
from nonebot_plugin_alconna import (
    CustomNode,
    Reference,
    RefNode,
    Segment,
    Text,
    UniMessage,
)

from .config import ForwardsConfig

type ForwardReferenceResolver = Callable[[str], Awaitable[Sequence[UniMessage]]]


class ForwardInputError(ValueError):
    """A safely categorized forwarded-message input failure."""


class ForwardFetchError(ForwardInputError):
    """The adapter could not return the referenced forwarded message."""


class ForwardLimitError(ForwardInputError):
    """Expanded forwarded content exceeded a configured safety limit."""


class ForwardUnsupportedError(ForwardInputError):
    """The adapter or Reference shape cannot be expanded safely."""


@dataclass(slots=True)
class _ExpansionState:
    config: ForwardsConfig
    resolver: ForwardReferenceResolver
    references: int = 0
    nodes: int = 0
    segments: int = 0
    text_chars: int = 0
    node_serial: int = 0
    cache: dict[str, tuple[UniMessage, ...]] = field(default_factory=dict)
    active_ids: set[str] = field(default_factory=set)

    async def expand(self, message: UniMessage, *, depth: int = 0) -> UniMessage:
        expanded = UniMessage()
        for segment in message:
            if isinstance(segment, Reference):
                expanded.extend(await self._expand_reference(segment, depth=depth))
                continue
            if depth:
                self._measure_segment(segment)
            expanded.append(segment)
        return expanded

    async def _expand_reference(
        self, reference: Reference, *, depth: int
    ) -> UniMessage:
        self.references += 1
        if self.references > self.config.max_references:
            raise ForwardLimitError("too many forwarded-message references")
        if depth >= self.config.max_depth:
            raise ForwardLimitError("forwarded-message nesting is too deep")

        active_id: str | None = None
        try:
            if reference.children:
                node_messages = tuple(
                    self._inline_node_content(node) for node in reference.children
                )
            elif reference.id:
                active_id = reference.id.strip()
                if not active_id:
                    raise ForwardUnsupportedError(
                        "forwarded-message reference ID is empty"
                    )
                if active_id in self.active_ids:
                    raise ForwardLimitError("cyclic forwarded-message reference")
                self.active_ids.add(active_id)
                node_messages = await self._resolve_id(active_id)
            else:
                raise ForwardUnsupportedError(
                    "forwarded message has no nodes or reference ID"
                )
            if not node_messages:
                raise ForwardFetchError(
                    "forwarded message contains no retrievable nodes"
                )

            expanded = UniMessage()
            for node_message in node_messages:
                self.nodes += 1
                if self.nodes > self.config.max_nodes:
                    raise ForwardLimitError("forwarded message contains too many nodes")
                self.node_serial += 1
                expanded.append(Text(f"\nForwarded message {self.node_serial}:\n"))
                expanded.extend(await self.expand(node_message.copy(), depth=depth + 1))
                expanded.append(Text("\n"))
            return expanded
        finally:
            if active_id is not None:
                self.active_ids.discard(active_id)

    def _inline_node_content(self, node: RefNode | CustomNode) -> UniMessage:
        if isinstance(node, RefNode):
            raise ForwardUnsupportedError(
                "reference-only forwarded nodes are unsupported"
            )
        content = node.content
        if isinstance(content, str):
            return UniMessage.text(content)
        if isinstance(content, UniMessage):
            return content.copy()
        if isinstance(content, list) and all(
            isinstance(item, Segment) for item in content
        ):
            return UniMessage(content).copy()
        raise ForwardUnsupportedError("forwarded node content has an unsupported shape")

    async def _resolve_id(self, reference_id: str) -> tuple[UniMessage, ...]:
        if cached := self.cache.get(reference_id):
            return tuple(message.copy() for message in cached)

        resolved = tuple(await self.resolver(reference_id))
        if not resolved or any(
            not isinstance(message, UniMessage) for message in resolved
        ):
            raise ForwardFetchError(
                "adapter returned no usable forwarded-message nodes"
            )
        cached = tuple(message.copy() for message in resolved)
        self.cache[reference_id] = cached
        return tuple(message.copy() for message in cached)

    def _measure_segment(self, segment: Segment) -> None:
        self.segments += 1
        if self.segments > self.config.max_segments:
            raise ForwardLimitError("forwarded message contains too many segments")
        if isinstance(segment, Text):
            self.text_chars += len(segment.text)
            if self.text_chars > self.config.max_text_chars:
                raise ForwardLimitError("forwarded-message text is too long")
        for child in segment.children:
            if isinstance(child, Reference):
                raise ForwardUnsupportedError(
                    "nested Reference children are unsupported"
                )
            self._measure_segment(child)


async def _resolve_adapter_reference(
    bot: Bot,
    reference_id: str,
    *,
    timeout_seconds: float,
) -> tuple[UniMessage, ...]:
    if bot.adapter.get_name() != "Milky":
        raise ForwardUnsupportedError(
            "adapter does not expose forwarded-message retrieval"
        )

    from nonebot.adapters.milky import Bot as MilkyBot

    if not isinstance(bot, MilkyBot):
        raise ForwardUnsupportedError("Milky adapter bot type is unavailable")
    try:
        async with asyncio.timeout(timeout_seconds):
            forwarded = await bot.get_forwarded_messages(forward_id=reference_id)
    except asyncio.CancelledError:
        raise
    except Exception as error:
        raise ForwardFetchError("Milky forwarded-message retrieval failed") from error
    if not forwarded:
        raise ForwardFetchError("Milky returned an empty forwarded message")
    try:
        return tuple(UniMessage.of(item.message, bot=bot) for item in forwarded)
    except Exception as error:
        raise ForwardUnsupportedError(
            "Milky returned unsupported forwarded content"
        ) from error


async def expand_forward_inputs(
    content: UniMessage,
    quoted: UniMessage | None,
    *,
    bot: Bot,
    config: ForwardsConfig,
    resolver: ForwardReferenceResolver | None = None,
) -> tuple[UniMessage, UniMessage | None]:
    """Expand inline and adapter-backed Reference segments under shared limits."""

    active_resolver = resolver or (
        lambda reference_id: _resolve_adapter_reference(
            bot,
            reference_id,
            timeout_seconds=config.fetch_timeout_seconds,
        )
    )
    state = _ExpansionState(config=config, resolver=active_resolver)
    expanded_content = await state.expand(content.copy())
    expanded_quoted = await state.expand(quoted.copy()) if quoted is not None else None
    return expanded_content, expanded_quoted


__all__ = [
    "ForwardFetchError",
    "ForwardInputError",
    "ForwardLimitError",
    "ForwardReferenceResolver",
    "ForwardUnsupportedError",
    "expand_forward_inputs",
]
