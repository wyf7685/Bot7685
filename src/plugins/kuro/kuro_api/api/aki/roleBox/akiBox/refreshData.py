# ruff: noqa: N815

from typing import override

from .....common import RequestInfo, WebRequest
from .....const import GameId


class WuwaRefreshDataRequest(WebRequest[bool]):
    """刷新数据 (?)"""

    gameId: GameId
    roleId: str
    serverId: str
    channelId: int = 19
    countryCode: int = 1

    @override
    def get_info(self) -> RequestInfo:
        return RequestInfo(
            url="https://api.kurobbs.com/aki/roleBox/akiBox/refreshData",
            method="POST",
        )

    @override
    def get_response_data_class(self) -> type[bool]:
        return bool
