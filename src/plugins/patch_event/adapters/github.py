from collections.abc import Callable, Iterable
from typing import Any, override

from githubkit.utils import UNSET
from nonebot.adapters.github import Event

from src.highlight import Highlight

from ..patcher import patcher


@patcher.bind
class H(Highlight):
    exclude_value = (UNSET,)

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
    return H.apply(self)
