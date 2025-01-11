# ruff: noqa: N815

from typing import override

from ...common import Request, RequestInfo, ResponseData
from ...const import GameId


class SignInInfo(ResponseData):
    continueDays: int
    hasSignIn: bool


class SignInInfoRequest(Request[SignInInfo]):
    """社区签到信息"""

    gameId: GameId = GameId.PNS

    @override
    def get_info(self) -> RequestInfo:
        return RequestInfo(
            url="https://api.kurobbs.com/user/signIn/info",
            method="GET",
        )

    @override
    def get_response_data_class(self) -> type[SignInInfo]:
        return SignInInfo
