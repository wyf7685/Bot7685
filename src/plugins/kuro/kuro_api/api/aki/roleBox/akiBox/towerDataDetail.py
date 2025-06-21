from typing import final

from ....common import RequestInfo
from .towerIndex import WuwaTowerIndexRequest


@final
class WuwaTowerDataDetailRequest(WuwaTowerIndexRequest):
    """鸣潮逆境深塔数据详细信息"""

    _info_ = RequestInfo(
        url="https://api.kurobbs.com/aki/roleBox/akiBox/towerDataDetail",
        method="POST",
    )
