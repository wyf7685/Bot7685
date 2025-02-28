# ruff: noqa: N815

from typing import final

from ...const import GameId
from ..common import Request, RequestInfo, ResponseData


class SignIn(ResponseData):
    class _GainVo(ResponseData):
        gainTyp: int
        gainValue: int

    continueDays: int
    gainVoList: list[_GainVo]


@final
class SignInRequest(Request[SignIn]):
    """社区签到"""

    _info_ = RequestInfo(url="https://api.kurobbs.com/user/signIn", method="POST")
    _resp_ = SignIn

    gameId: GameId = GameId.PNS
