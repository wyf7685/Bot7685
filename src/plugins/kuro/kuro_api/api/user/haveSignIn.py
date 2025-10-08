# ruff: noqa: N815

from typing import TYPE_CHECKING, final
from warnings import deprecated

from ..common import Request, RequestInfo

if TYPE_CHECKING:
    from ...const import GameId


@final
@deprecated("Use `SignInInfoRequest` instead")
class HaveSignInRequest(Request[bool]):
    """是否社区签到"""

    _info_ = RequestInfo(url="https://api.kurobbs.com/user/haveSignIn", method="POST")
    _resp_ = bool

    gameId: GameId
