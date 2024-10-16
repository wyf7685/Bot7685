import contextlib
from typing import Any, override

from nonebot.compat import model_dump

from ..patcher import Patcher
from ..utils import highlight_object


def exclude_unset_none(data: dict[str, Any] | list[Any]) -> dict[str, Any] | list[Any]:
    return (
        {
            k: (exclude_unset_none(v) if isinstance(v, dict | list) else v)
            for k, v in data.items()
            if v is not UNSET and v is not None
        }
        if isinstance(data, dict)
        else [
            (exclude_unset_none(i) if isinstance(i, dict | list) else i)
            for i in data
            if i is not UNSET and i is not None
        ]
    )


with contextlib.suppress(ImportError):
    from nonebot.adapters.discord import Event
    from nonebot.adapters.discord.api import UNSET

    @Patcher
    class PatchEvent(Event):
        @override
        def get_log_string(self) -> str:
            return (
                f"[{self.get_event_name()}] "
                f"{highlight_object(exclude_unset_none(model_dump(self)))}"
            )
