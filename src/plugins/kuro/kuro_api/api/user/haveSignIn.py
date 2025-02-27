# ruff: noqa: N815

from dataclasses import dataclass
from typing import final
from warnings import deprecated

from ...common import Request, RequestInfo
from ...const import GameId


@final
@deprecated("Use `SignInInfoRequest` instead")
@dataclass
class HaveSignInRequest(Request[bool]):
    """是否社区签到"""

    _info_ = RequestInfo(url="https://api.kurobbs.com/user/haveSignIn", method="POST")
    _resp_ = bool

    gameId: GameId
