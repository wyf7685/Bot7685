from collections.abc import Awaitable, Callable, Sequence

from nonebot.adapters import Bot, Event
from nonebot_plugin_alconna import Reference, UniMessage

type ForwardReferenceResolver = Callable[
    [Reference],
    Awaitable[Sequence[UniMessage]],
]
type AdapterReferenceResolver = Callable[
    [Bot, Event, Reference],
    Awaitable[Sequence[UniMessage]],
]


class ForwardInputError(ValueError):
    """A safely categorized forwarded-message input failure."""


class ForwardFetchError(ForwardInputError):
    """The adapter could not return the referenced forwarded message."""


class ForwardLimitError(ForwardInputError):
    """Expanded forwarded content exceeded a configured safety limit."""


class ForwardUnsupportedError(ForwardInputError):
    """The adapter or Reference shape cannot be expanded safely."""


__all__ = [
    "AdapterReferenceResolver",
    "ForwardFetchError",
    "ForwardInputError",
    "ForwardLimitError",
    "ForwardReferenceResolver",
    "ForwardUnsupportedError",
]
