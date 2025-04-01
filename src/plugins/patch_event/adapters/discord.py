import abc
from typing import ClassVar, override

import nonebot
from nonebot.adapters.discord import Event, Message
from nonebot.adapters.discord.api import UNSET, Channel, SnowflakeType
from nonebot.adapters.discord.event import (
    DirectMessageCreateEvent,
    DirectMessageUpdateEvent,
    GuildCreateEvent,
    GuildMessageCreateEvent,
    GuildMessageUpdateEvent,
)
from nonebot.compat import model_dump
from nonebot.utils import escape_tag

from ..highlight import Highlight as BaseHighlight
from ..patcher import Patcher

guild_name_cache: dict["SnowflakeType", str] = {}
guild_channel_cache: dict["SnowflakeType", list["Channel"]] = {}


def find_guild_name(guild: "SnowflakeType") -> str | None:
    return guild_name_cache.get(guild)


def find_channel_name(guild: "SnowflakeType", channel: "SnowflakeType") -> str | None:
    for c in guild_channel_cache.get(guild, []):
        if c.id == channel:
            return c.name or None
    return None


class Highlight(BaseHighlight):
    exclude_value: ClassVar[tuple[object, ...]] = (UNSET, None)


@Patcher
class PatchEvent(Event, abc.ABC):
    @override
    def get_log_string(self) -> str:
        return f"[{self.get_event_name()}] {Highlight.apply(model_dump(self))}"


@Patcher
class PatchDirectMessageCreateEvent(DirectMessageCreateEvent):
    @override
    def get_log_string(self) -> str:
        return (
            f"[{self.get_event_name()}] "
            f"Message <c>{self.id}</c> from "
            f"<y>{escape_tag(self.author.global_name or self.author.username)}</y>"
            f"(<c>{self.author.id}</c>) "
            f"{Highlight.apply(self.get_message())}"
        )


@Patcher
class PatchDirectMessageUpdateEvent(DirectMessageUpdateEvent):
    @override
    def get_log_string(self) -> str:
        return (
            f"[{self.get_event_name()}] "
            f"Message <c>{self.id}</c> from "
            f"<y>{escape_tag(self.author.global_name or self.author.username)}</y>"
            f"(<c>{self.author.id}</c>) updated to "
            f"{Highlight.apply(Message.from_guild_message(self))}"
        )


@Patcher
class PatchGuildMessageCreateEvent(GuildMessageCreateEvent):
    @override
    def get_log_string(self) -> str:
        guild = f"<c>{self.guild_id}</c>"
        if name := find_guild_name(self.guild_id):
            guild = f"<y>{escape_tag(name)}</y>({guild})"
        channel = f"<c>{self.channel_id}</c>"
        if name := find_channel_name(self.guild_id, self.channel_id):
            channel = f"<y>{escape_tag(name)}</y>({channel})"

        return (
            f"[{self.get_event_name()}] "
            f"Message <c>{self.id}</c> from "
            f"<y>{escape_tag(self.author.global_name or self.author.username)}</y>"
            f"(<c>{self.author.id}</c>)"
            f"@[Guild:{guild} Channel:{channel}] "
            f"{Highlight.apply(self.get_message())}"
        )


@Patcher
class PatchGuildMessageUpdateEvent(GuildMessageUpdateEvent):
    @override
    def get_log_string(self) -> str:
        guild = f"<c>{self.guild_id}</c>"
        if name := find_guild_name(self.guild_id):
            guild = f"<y>{escape_tag(name)}</y>({guild})"
        channel = f"<c>{self.channel_id}</c>"
        if name := find_channel_name(self.guild_id, self.channel_id):
            channel = f"<y>{escape_tag(name)}</y>({channel})"

        return (
            f"[{self.get_event_name()}] "
            f"Message <c>{self.id}</c> from "
            f"<y>{escape_tag(self.author.global_name or self.author.username)}</y>"
            f"(<c>{self.author.id}</c>)"
            f"@[Guild:{guild} Channel:{channel}] updated to "
            f"{Highlight.apply(Message.from_guild_message(self))}"
        )


@nonebot.on_type(GuildCreateEvent).handle()
async def _(event: GuildCreateEvent) -> None:
    if event.name is not UNSET:
        guild_name_cache[event.id] = event.name
    if event.channels is not UNSET:
        guild_channel_cache[event.id] = event.channels
