import contextlib
from typing import Any, override

import nonebot
from nonebot.compat import model_dump
from nonebot.utils import escape_tag

from ..patcher import Patcher
from ..utils import Highlight


def exclude_unset_none(data: dict[str, Any] | list[Any]) -> dict[str, Any] | list[Any]:
    if isinstance(data, dict):
        return {
            k: (exclude_unset_none(v) if isinstance(v, dict | list) else v)
            for k, v in data.items()
            if v is not UNSET and v is not None
        }
    return [
        (exclude_unset_none(i) if isinstance(i, dict | list) else i)
        for i in data
        if i is not UNSET and i is not None
    ]


guild_name_cache: dict[int, str] = {}
guild_channel_cache: dict[int, list["Channel"]] = {}


def find_guild_name(guild: int) -> str | None:
    return guild_name_cache.get(guild)


def find_channel_name(guild: int, channel: int) -> str | None:
    for c in guild_channel_cache.get(guild, []):
        if c.id == channel:
            return c.name or None
    return None


with contextlib.suppress(ImportError):
    from nonebot.adapters.discord import Event
    from nonebot.adapters.discord.api import UNSET, Channel
    from nonebot.adapters.discord.event import (
        DirectMessageCreateEvent,
        GuildCreateEvent,
        GuildMessageCreateEvent,
    )

    @Patcher
    class PatchEvent(Event):
        @override
        def get_log_string(self) -> str:
            return (
                f"[{self.get_event_name()}] "
                f"{Highlight.object(exclude_unset_none(model_dump(self)))}"
            )

    @Patcher
    class PatchDirectMessageCreateEvent(DirectMessageCreateEvent):
        @override
        def get_log_string(self) -> str:
            return (
                f"[{self.get_event_name()}] "
                f"Message <c>{self.id}</c> from "
                f"<y>{escape_tag(self.author.global_name or self.author.username)}</y>"
                f"(<c>{self.author.id}</c>) "
                f"{Highlight.message(self.get_message())}"
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
                f"{Highlight.message(self.get_message())}"
            )

    @nonebot.on_type(GuildCreateEvent).handle()
    async def _(event: GuildCreateEvent) -> None:
        if event.name is not UNSET:
            guild_name_cache[event.id] = event.name
        if event.channels is not UNSET:
            guild_channel_cache[event.id] = event.channels
