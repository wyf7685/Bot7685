from collections.abc import Callable, Iterable
from typing import Any, override

from nonebot.adapters.github import Event

from ..highlight import Highlight
from ..patcher import patcher


class H(Highlight):
    @override
    @classmethod
    def _kv(
        cls,
        items: Iterable[tuple[str, Any]],
        separator: str,
        format_key: Callable[[str], str],
        /,
    ) -> Iterable[str]:
        filtered = filter(lambda item: not item[0].endswith("_url"), items)
        yield from super()._kv(filtered, separator, format_key)


@patcher
def patch_event(self: Event) -> str:
    return f"\n{H.apply(self, indent=2, line_length=180)}"
