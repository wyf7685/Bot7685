# ruff: noqa: N815

from dataclasses import dataclass
from typing import final

from ...common import Request, RequestInfo, ResponseData
from ...const import GameId


class SignInInfo(ResponseData):
    continueDays: int
    hasSignIn: bool


@final
@dataclass
class SignInInfoRequest(Request[SignInInfo]):
    """社区签到信息"""

    _info_ = RequestInfo(
        url="https://api.kurobbs.com/user/signIn/info",
        method="GET",
    )
    _resp_ = SignInInfo

    gameId: GameId = GameId.PNS
