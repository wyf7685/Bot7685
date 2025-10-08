from typing import TYPE_CHECKING

from ..kuro_api import GameId
from .alc import root_matcher

if TYPE_CHECKING:
    from .depends import HandlerFromKey

matcher_signin = root_matcher.dispatch("signin")


@matcher_signin.assign("~kuro")
async def assign_kuro(handler: HandlerFromKey) -> None:
    await handler.kuro_signin()
    await handler.push_msg()


@matcher_signin.assign("~pns")
async def assign_pns(handler: HandlerFromKey) -> None:
    await handler.game_signin(GameId.PNS)
    await handler.push_msg()


@matcher_signin.assign("~wuwa")
async def assign_wuwa(handler: HandlerFromKey) -> None:
    await handler.game_signin(GameId.WUWA)
    await handler.push_msg()
