# ruff: noqa: N815

from enum import Enum
from typing import TYPE_CHECKING, final

from pydantic import Field

from ...common import RequestInfo, ResponseData, WebRequest

if TYPE_CHECKING:
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
    signInDate: str = Field(alias="sigInDate")
    """签到日期"""
    type: GoodsType | int
    """
    签到类型

    0 = 普通签到, 2 = 新手一次性签到活动, 3 = 限时签到
    """

    @property
    def signin_type(self) -> str:
        return {
            GoodsType.NORMAL.value: "签到",
            GoodsType.NEWBIE.value: "新手签到",
            GoodsType.TIMED.value: "限时签到",
        }.get(int(self.type), "特殊签到")


QueryRecordV2 = list[GoodsData]


@final
class QueryRecordV2Request(WebRequest[QueryRecordV2]):
    """取游戏签到记录 V2"""

    _info_ = RequestInfo(
        url="https://api.kurobbs.com/encourage/signIn/queryRecordV2", method="POST"
    )
    _resp_ = QueryRecordV2

    gameId: GameId
    serverId: str
    roleId: str
    userId: str
