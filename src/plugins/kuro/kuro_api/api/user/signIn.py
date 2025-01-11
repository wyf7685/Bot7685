# ruff: noqa: N815

from typing import override

from ...common import Request, RequestInfo, ResponseData
from ...const import GameId


class SignIn(ResponseData):
    class _GainVo(ResponseData):
        gainTyp: int
        gainValue: int

    continueDays: int
    gainVoList: list[_GainVo]


class SignInRequest(Request[SignIn]):
    """社区签到"""

    gameId: GameId = GameId.PNS

    @override
    def get_info(self) -> RequestInfo:
        return RequestInfo(url="https://api.kurobbs.com/user/signIn", method="POST")

    @override
    def get_response_data_class(self) -> type[SignIn]:
        return SignIn
