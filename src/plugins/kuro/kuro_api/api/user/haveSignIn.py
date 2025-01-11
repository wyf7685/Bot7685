# ruff: noqa: N815

from typing import override
from warnings import deprecated

from ...common import Request, RequestInfo
from ...const import GameId


@deprecated("Use `SignInInfoRequest` instead")
class HaveSignInRequest(Request[bool]):
    """是否社区签到"""

    gameId: GameId

    @override
    def get_info(self) -> RequestInfo:
        return RequestInfo(url="https://api.kurobbs.com/user/haveSignIn", method="POST")

    @override
    def get_response_data_class(self) -> type[bool]:
        return bool
