from typing import ClassVar, Protocol

from nonebot.adapters.discord import Event, Message
from nonebot.adapters.discord.api import UNSET, Channel, SnowflakeType, User
from nonebot.adapters.discord.api.types import Unset
from nonebot.adapters.discord.event import (
    DirectMessageCreateEvent,
    DirectMessageDeleteEvent,
    DirectMessageUpdateEvent,
    GuildCreateEvent,
    GuildMessageCreateEvent,
    GuildMessageDeleteEvent,
    GuildMessageUpdateEvent,
)
from nonebot.compat import model_dump
from nonebot.message import event_preprocessor

from ..highlight import Highlight
from ..patcher import patcher

guild_name_cache: dict[SnowflakeType, str] = {}
guild_channel_cache: dict[SnowflakeType, list[Channel]] = {}


def find_guild_name(guild: SnowflakeType) -> str | None:
    return guild_name_cache.get(guild)


def find_channel_name(guild: SnowflakeType, channel: SnowflakeType) -> str | None:
    for c in guild_channel_cache.get(guild, []):
        if c.id == channel:
            return c.name or None
    return None


@event_preprocessor
async def _(event: GuildCreateEvent) -> None:
    if event.name is not UNSET:
        guild_name_cache[event.id] = event.name
    if event.channels is not UNSET:
        guild_channel_cache[event.id] = event.channels


class EventWithChannel(Protocol):
    @property
    def channel_id(self) -> SnowflakeType: ...
    @property
    def guild_id(self) -> SnowflakeType: ...


class H(Highlight):
    exclude_value: ClassVar[tuple[object, ...]] = (UNSET, None)

    @classmethod
    def user(cls, user: User | Unset) -> str:
        return (
            cls.name(user.id, user.global_name or user.username)
            if user is not UNSET
            else "<unknown user>"
        )

    @classmethod
    def channel(cls, event: EventWithChannel) -> str:
        guild = cls.name(event.guild_id, find_guild_name(event.guild_id))
        channel = cls.name(
            event.channel_id,
            find_channel_name(event.guild_id, event.channel_id),
        )
        return f"[Guild:{guild} Channel:{channel}]"


@patcher
def patch_event(self: Event) -> str:
    return H.apply(model_dump(self))


@patcher
def patch_direct_message_create_event(self: DirectMessageCreateEvent) -> str:
    return (
        f"Message {H.id(self.id)} "
        f"from {H.user(self.author)}: "
        f"{H.apply(self.get_message())}"
    )


@patcher
def patch_direct_message_update_event(self: DirectMessageUpdateEvent) -> str:
    return (
        f"Message {H.id(self.id)} "
        f"from {H.user(self.author)} "
        f"updated to {H.apply(Message.from_guild_message(self))}"
    )


@patcher
def patch_direct_message_delete_event(self: DirectMessageDeleteEvent) -> str:
    return (
        f"Message {H.id(self.id)} "
        f"from {H.id(self.channel_id)} "
        f"deleted at {H.time(self.time)}"
    )


@patcher
def patch_guild_message_create_event(self: GuildMessageCreateEvent) -> str:
    return (
        f"Message {H.id(self.id)} "
        f"from {H.user(self.author)}@{H.channel(self)}: "
        f"{H.apply(self.get_message())}"
    )


@patcher
def patch_guild_message_update_event(self: GuildMessageUpdateEvent) -> str:
    return (
        f"Message {H.id(self.id)} "
        f"from {H.user(self.author)}@{H.channel(self)} "
        f"updated to {H.apply(Message.from_guild_message(self))}"
    )


@patcher
def patch_guild_message_delete_event(self: GuildMessageDeleteEvent) -> str:
    return (
        f"Message {H.id(self.id)} from {H.channel(self)} deleted at {H.time(self.time)}"
    )
