# ruff: noqa: N815

from typing import final

from .....const import GameId, WuwaGameId
from ....common import RequestInfo, WebRequest


@final
class WuwaUpdateShowSettingRequest(WebRequest[bool]):
    _info_ = RequestInfo(
        url="https://api.kurobbs.com/aki/roleBox/akiBox/updateShowSetting",
        method="POST",
    )
    _resp_ = bool

    roleId: str
    serverId: str
    type: int
    """参考 `aki/roleBox/akiBox/getShowSettings` 返回值的 code 字段"""
    open: bool
    gameId: WuwaGameId = GameId.WUWA
    channelId: int = 19
    countryCode: int = 1
