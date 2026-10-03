import re
from urllib.parse import urlsplit

from nonebot.adapters import Bot, Event
from nonebot.adapters.discord.api.model import Embed as DiscordEmbed
from nonebot.adapters.discord.api.model import MessageGet as DiscordMessageGet
from nonebot.adapters.discord.message import EmbedSegment as DiscordEmbedSegment
from nonebot.adapters.discord.message import Message as DiscordMessage
from nonebot_plugin_alconna.uniseg import Other, Reply, Text, UniMessage

_MAX_EMBED_CHARS = 4096
_MAX_EMBED_TITLE_CHARS = 256
_MAX_EMBED_DESCRIPTION_CHARS = 1024
_MAX_EMBED_NAME_CHARS = 128
_MAX_EMBED_FIELD_COUNT = 8
_MAX_EMBED_FIELD_VALUE_CHARS = 512
_MAX_EMBED_URL_CHARS = 2048
_HTTP_URL_RE = re.compile(r"https?://[^\s<>]+", re.IGNORECASE)
_URL_TRAILING_PUNCTUATION = ".,!?:;\"'"


def quoted_message_from_event(
    bot: Bot,
    event: Event,
    reply: Reply,
) -> UniMessage | None:
    referenced_message = getattr(event, "referenced_message", None)
    if not isinstance(referenced_message, DiscordMessageGet):
        return None

    reference = getattr(event, "message_reference", None)
    reference_id = getattr(reference, "message_id", None)
    reply_id = str(reply.id)
    if str(reference_id) != reply_id or str(referenced_message.id) != reply_id:
        return None

    native_message = DiscordMessage.from_guild_message(referenced_message)
    return UniMessage.of(native_message, bot=bot).copy()


def normalize_message(message: UniMessage) -> UniMessage:
    if not any(
        isinstance(segment, Other) and isinstance(segment.origin, DiscordEmbedSegment)
        for segment in message
    ):
        return message

    source_text = "".join(
        segment.text for segment in message if isinstance(segment, Text)
    )
    normalized = UniMessage()
    for segment in message:
        if isinstance(segment, Other):
            embed_text = _render_embed(segment, source_text)
            if embed_text is not None:
                if embed_text:
                    normalized.append(Text(embed_text))
                continue
        normalized.append(segment)
    return normalized


def _render_embed(segment: Other, source_text: str) -> str | None:
    origin = segment.origin
    if not isinstance(origin, DiscordEmbedSegment):
        return None
    embed = origin.data.get("embed")
    if not isinstance(embed, DiscordEmbed):
        return None

    embed_url = _as_text(embed.url)
    if embed_url and _text_contains_url(source_text, embed_url):
        return ""

    parts: list[str] = []
    title = _bounded_text(embed.title, _MAX_EMBED_TITLE_CHARS)
    description = _bounded_text(embed.description, _MAX_EMBED_DESCRIPTION_CHARS)
    if title:
        parts.append(title)
    if description:
        parts.append(description)

    author = getattr(embed, "author", None)
    author_name = _bounded_text(getattr(author, "name", None), _MAX_EMBED_NAME_CHARS)
    if author_name:
        parts.append(f"Author: {author_name}")

    provider = getattr(embed, "provider", None)
    provider_name = _bounded_text(
        getattr(provider, "name", None), _MAX_EMBED_NAME_CHARS
    )
    if provider_name:
        parts.append(f"Provider: {provider_name}")

    safe_url = _safe_http_url(embed_url)
    if safe_url:
        parts.append(safe_url)

    fields = getattr(embed, "fields", None)
    if isinstance(fields, list):
        for field in fields[:_MAX_EMBED_FIELD_COUNT]:
            name = _bounded_text(getattr(field, "name", None), _MAX_EMBED_NAME_CHARS)
            value = _bounded_text(
                getattr(field, "value", None), _MAX_EMBED_FIELD_VALUE_CHARS
            )
            if name and value:
                parts.append(f"{name}: {value}")
            elif name or value:
                parts.append(name or value)

    rendered = "\n".join(parts)
    return _bounded_text(rendered, _MAX_EMBED_CHARS) or None


def _as_text(value: object) -> str:
    return value if isinstance(value, str) else ""


def _bounded_text(value: object, limit: int) -> str:
    text = _as_text(value).strip()
    if len(text) <= limit:
        return text
    return f"{text[: limit - 1].rstrip()}…"


def _text_contains_url(text: str, url: str) -> bool:
    return any(_trim_url(match.group()) == url for match in _HTTP_URL_RE.finditer(text))


def _trim_url(url: str) -> str:
    trimmed = url.rstrip(_URL_TRAILING_PUNCTUATION)
    for closing, opening in ((")", "("), ("]", "["), ("}", "{")):
        while trimmed.endswith(closing) and trimmed.count(closing) > trimmed.count(
            opening
        ):
            trimmed = trimmed[:-1]
    return trimmed


def _safe_http_url(url: str) -> str | None:
    if not url or len(url) > _MAX_EMBED_URL_CHARS:
        return None
    try:
        parsed = urlsplit(url)
        _ = parsed.port
    except ValueError:
        return None
    if (
        parsed.scheme.casefold() not in {"http", "https"}
        or parsed.hostname is None
        or parsed.username is not None
        or parsed.password is not None
    ):
        return None
    return url
