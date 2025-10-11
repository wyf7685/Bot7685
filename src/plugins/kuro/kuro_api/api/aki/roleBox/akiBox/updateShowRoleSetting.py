# ruff: noqa: N815

from collections.abc import Sequence
from typing import final, override

from .....const import GameId, WuwaGameId
from ....common import RequestInfo, WebRequest


@final
class WuwaUpdateShowRoleSettingRequest(WebRequest[bool]):
    _info_ = RequestInfo(
        url="https://api.kurobbs.com/aki/roleBox/akiBox/updateShowRoleSetting",
        method="POST",
    )
    _resp_ = bool

    roleId: str
    serverId: str
    showRoleIds: Sequence[int]
    gameId: WuwaGameId = GameId.WUWA
    channelId: int = 19
    countryCode: int = 1

    @override
    def dump(self) -> dict[str, object]:
        data = super().dump()
        data["showRoleIds"] = ",".join(map(str, self.showRoleIds[:8]))
        return data
