from collections.abc import Callable
from typing import Any, cast

import nonebot
from nonebot.adapters import Event
from nonebot.utils import escape_tag

logger = nonebot.logger.opt(colors=True)
_PATCHERS: set["Patcher"] = set()


@nonebot.get_driver().on_startup
async def _() -> None:
    for patcher in _PATCHERS:
        patcher.patch()


class Patcher[T: Event]:
    __target: type
    __name: str
    __patched: dict[str, tuple[Callable[..., Any], Callable[..., Any]]]
    origin: type[T]
    patcher: type[T]

    def __init__(self, cls: type[T]) -> None:
        self.__target = cls.mro()[1]
        self.__name = self.__target.__name__
        self.__patched = {
            name: (patched, original)
            for name, patched in cls.__dict__.items()
            if not name.startswith("model_")
            and callable(patched)
            and hasattr(self.__target, name)
            and callable(original := getattr(self.__target, name))
            and original is not patched
        }
        origin = type(
            self.__name,
            (self.__target,),
            {name: original for name, (_, original) in self.__patched.items()},
        )
        self.origin = cast(type[T], origin)
        self.patcher = cls
        _PATCHERS.add(self)

    def patch(self) -> None:
        for name, (patched, _) in self.__patched.items():
            colored = f"<g>{self.__name}</g>.<y>{name}</y>"
            try:
                setattr(self.__target, name, patched)
            except Exception as err:
                err = f"<r>{escape_tag(repr(err))}</r>"
                logger.warning(f"Patch {colored} failed: {err}")
            else:
                logger.debug(f"Patch {colored}")

    def restore(self) -> None:
        for name, (_, original) in self.__patched.items():
            colored = f"<g>{self.__name}</g>.<y>{name}</y>"
            try:
                setattr(self.__target, name, original)
            except Exception as err:
                err = f"<r>{escape_tag(repr(err))}</r>"
                logger.warning(f"Restore {colored} failed: {err}")
            else:
                logger.debug(f"Restore {colored}")
