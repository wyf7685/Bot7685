# ruff: noqa: N815

from typing import override

from .....common import RequestInfo
from .towerIndex import WuwaTowerIndexRequest


class WuwaTowerDataDetailRequest(WuwaTowerIndexRequest):
    """鸣潮逆境深塔数据详细信息"""

    @override
    def get_info(self) -> RequestInfo:
        return RequestInfo(
            url="https://api.kurobbs.com/aki/roleBox/akiBox/towerDataDetail",
            method="POST",
        )
