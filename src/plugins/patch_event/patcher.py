from collections.abc import Callable
from typing import Any, cast

import nonebot
from nonebot.utils import escape_tag

logger = nonebot.logger.opt(colors=True)


class Patcher[T: type]:
    target: type
    name: str
    patched: dict[str, tuple[Callable[..., Any], Callable[..., Any]]]
    origin: T

    def __init__(self, cls: T) -> None:
        self.target = target = cls.mro()[1]
        self.name = target.__name__
        self.patched = {
            name: (patched, original)
            for name, patched in cls.__dict__.items()
            if not name.startswith("model_")
            and callable(patched)
            and (original := getattr(target, name, ...)) is not ...
            and callable(original)
            and original is not patched
        }
        origin = type(
            self.name,
            (target,),
            {name: original for name, (_, original) in self.patched.items()},
        )
        self.origin = cast(T, origin)
        nonebot.get_driver().on_startup(self.patch)

    def patch(self) -> None:
        for name, (patched, _) in self.patched.items():
            colored = f"<g>{self.name}</g>.<y>{name}</y>"
            try:
                setattr(self.target, name, patched)
            except Exception as err:
                err = f"<r>{escape_tag(repr(err))}</r>"
                logger.warning(f"Patch {colored} failed: {err}")
            else:
                logger.success(f"Patch {colored}")

    def restore(self) -> None:
        for name, (_, original) in self.patched.items():
            colored = f"<g>{self.name}</g>.<y>{name}</y>"
            try:
                setattr(self.target, name, original)
            except Exception as err:
                err = f"<r>{escape_tag(repr(err))}</r>"
                logger.warning(f"Restore {colored} failed: {err}")
            else:
                logger.success(f"Restore {colored}")
