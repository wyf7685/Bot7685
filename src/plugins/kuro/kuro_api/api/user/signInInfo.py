# ruff: noqa: N815

from typing import final

from ...const import GameId
from ..common import Request, RequestInfo, ResponseData


class SignInInfo(ResponseData):
    continueDays: int
    hasSignIn: bool


@final
class SignInInfoRequest(Request[SignInInfo]):
    """社区签到信息"""

    _info_ = RequestInfo(
        url="https://api.kurobbs.com/user/signIn/info",
        method="GET",
    )
    _resp_ = SignInInfo

    gameId: GameId = GameId.PNS
