# ruff: noqa: N815

from dataclasses import dataclass
from typing import final, override

from ....common import RequestInfo, Response, ResponseData, WebRequest
from ....const import GameId


class GoodsData(ResponseData):
    goodsId: int
    """物品 id"""
    goodsNum: int
    """物品数量"""
    goodsUrl: str
    """物品图标链接"""
    type: int


class SignInV2(ResponseData):
    todayList: list[GoodsData]
    """今天签到获得的物品信息"""
    tomorrowList: list[GoodsData]
    """明天签到获得的物品信息"""


@final
@dataclass
class SigninV2Request(WebRequest[SignInV2]):
    """取游戏签到记录 V2"""

    _info_ = RequestInfo(
        url="https://api.kurobbs.com/encourage/signIn/v2", method="POST"
    )
    _resp_ = SignInV2

    gameId: GameId
    serverId: str
    roleId: str
    userId: str
    reqMonth: int | str
    """签到的月份"""

    @override
    async def send(self, token: str) -> Response[SignInV2]:
        self.reqMonth = str(self.reqMonth).zfill(2)
        return await super().send(token)
