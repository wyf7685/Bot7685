# ruff: noqa: N815

from typing import final

from ...common import Request, RequestInfo, ResponseData


class TimingSwitchResponse(ResponseData):
    openGame3RoleBox: bool
    enterVideoPostGame3: bool
    enterVideoPostGame2: bool
    openRoleBox: bool
    openGame3Scan: bool
    bindRoleGame2: bool
    systemTime: int
    bindRoleGame3: bool
    openGameScan: bool



@final
class TimingSwitchRequest(Request[TimingSwitchResponse]):
    _info_ = RequestInfo(
        url="https://api.kurobbs.com/config/dict/timingSwitch",
        method="GET",
    )
    _resp_ = TimingSwitchResponse
