# ruff: noqa: N815

from dataclasses import dataclass
from typing import final

from ...common import Request, RequestInfo, ResponseData
from ...const import GameId


class SignIn(ResponseData):
    class _GainVo(ResponseData):
        gainTyp: int
        gainValue: int

    continueDays: int
    gainVoList: list[_GainVo]


@final
@dataclass
class SignInRequest(Request[SignIn]):
    """社区签到"""

    _info_ = RequestInfo(url="https://api.kurobbs.com/user/signIn", method="POST")
    _resp_ = SignIn

    gameId: GameId = GameId.PNS
