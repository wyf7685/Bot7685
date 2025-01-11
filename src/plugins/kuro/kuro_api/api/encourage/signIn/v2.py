# ruff: noqa: N815

from typing import override

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


class SigninV2Request(WebRequest[SignInV2]):
    """取游戏签到记录 V2"""

    gameId: GameId
    serverId: str
    roleId: str
    userId: str
    reqMonth: int | str
    """签到的月份"""

    @override
    def get_info(self) -> RequestInfo:
        return RequestInfo(
            url="https://api.kurobbs.com/encourage/signIn/v2",
            method="POST",
        )

    @override
    def get_response_data_class(self) -> type[SignInV2]:
        return SignInV2

    @override
    async def send(self, token: str) -> Response[SignInV2]:
        self.reqMonth = str(self.reqMonth).zfill(2)
        return await super().send(token)
