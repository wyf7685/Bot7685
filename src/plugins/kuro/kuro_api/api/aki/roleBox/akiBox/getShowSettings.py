# ruff: noqa: N815

from typing import final

from .....const import GameId, WuwaGameId
from ....common import RequestInfo, ResponseData, WebRequest


class ShowSetting(ResponseData):
    code: int
    name: str
    open: bool


@final
class WuwaGetShowSettingsRequest(WebRequest[list[ShowSetting]]):
    _info_ = RequestInfo(
        url="https://api.kurobbs.com/aki/roleBox/akiBox/getShowSettings",
        method="POST",
    )
    _resp_ = list[ShowSetting]

    roleId: str
    serverId: str
    gameId: WuwaGameId = GameId.WUWA
