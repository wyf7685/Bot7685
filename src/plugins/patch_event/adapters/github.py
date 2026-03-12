import re
from collections.abc import Iterable
from typing import override

from nonebot.adapters.github import Event

from ..highlight import Highlight
from ..patcher import patcher

pattern_url = re.compile(f"^{Highlight.style.i_y('[a-z_]+_url')}=")


class H(Highlight):
    @override
    @classmethod
    def _seq(cls, seq: Iterable[str], bracket: str, /) -> str:
        return super()._seq(
            (item for item in seq if not pattern_url.match(item)),
            bracket,
        )


@patcher
def patch_event(self: Event) -> str:
    return f"\n{H.apply(self, indent=2)}"
