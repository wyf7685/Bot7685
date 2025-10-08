from typing import TYPE_CHECKING

from ..highlight import Highlight
from ..patcher import patcher

if TYPE_CHECKING:
    from nonebot.adapters.milky import Event


class H(Highlight): ...


@patcher
def patch_event(self: Event) -> str:
    return f"[{H.event_type(self.get_event_name())}]: {H.apply(self)}"


# TODO: impl when Milky gets stable
