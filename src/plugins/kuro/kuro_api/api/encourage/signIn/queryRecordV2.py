# ruff: noqa: N815

from enum import Enum
from typing import override

from ....common import RequestInfo, ResponseData, WebRequest
from ....const import GameId


class GoodsType(int, Enum):
    """物品类型"""

    NORMAL = 0
    """普通签到"""
    NEWBIE = 2
    """新手一次性签到活动"""
    TIMED = 3
    """限时签到"""

class GoodsData(ResponseData):
    goodsId: int
    """物品 id"""
    goodsName: str
    """物品名称"""
    goodsNum: int
    """物品数量"""
    goodsUrl: str
    """物品图标链接"""
    # id: int
    sendState: bool
    sendStateV2: int
    sigInDate: str
    """签到日期"""
    type: GoodsType
    """
    签到类型

    0 = 普通签到, 2 = 新手一次性签到活动, 3 = 限时签到
    """


QueryRecordV2 = list[GoodsData]


class QueryRecordV2Request(WebRequest[QueryRecordV2]):
    """取游戏签到记录 V2"""

    gameId: GameId
    serverId: str
    roleId: str
    userId: str

    @override
    def get_info(self) -> RequestInfo:
        return RequestInfo(
            url="https://api.kurobbs.com/encourage/signIn/queryRecordV2",
            method="POST",
        )

    @override
    def get_response_data_class(self) -> type[QueryRecordV2]:
        return QueryRecordV2
