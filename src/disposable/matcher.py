from typing import override

from nonebot.internal.matcher import Matcher

from .plugin import internal_dispose
from .utils import escape_tag, log


class DisposableMatcher(Matcher):
    @override
    def __init_subclass__(cls) -> None:
        if cls._source is not None and cls.plugin_id is not None:  # pyright:ignore[reportPrivateUsage]
            internal_dispose(cls.plugin_id, func=cls.destroy)
        return super().__init_subclass__()

    @override
    @classmethod
    def destroy(cls) -> None:
        log("TRACE", f"Destroying matcher {escape_tag(repr(cls))}")
        return super().destroy()


def setup_disposable() -> None:
    import sys

    import nonebot.internal.matcher
    import nonebot.internal.matcher.matcher
    import nonebot.matcher

    nonebot.matcher.Matcher = nonebot.internal.matcher.Matcher = (
        nonebot.internal.matcher.matcher.Matcher
    ) = DisposableMatcher
    sys.modules["nonebot.plugin.on"].Matcher = DisposableMatcher  # pyright:ignore[reportAttributeAccessIssue]
