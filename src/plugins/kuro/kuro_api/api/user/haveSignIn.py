# ruff: noqa: N815

from typing import final
from warnings import deprecated

from ...const import GameId
from ..common import Request, RequestInfo


@final
@deprecated("Use `SignInInfoRequest` instead")
class HaveSignInRequest(Request[bool]):
    """是否社区签到"""

    _info_ = RequestInfo(url="https://api.kurobbs.com/user/haveSignIn", method="POST")
    _resp_ = bool

    gameId: GameId
