# ruff: noqa: N815

from typing import Literal, override

from pydantic import Field

from .....common import RequestInfo, ResponseData, WebRequest
from .....const import GameId, WuwaGameId

type DataName = Literal["结晶波片", "活跃度", "电台等级", "本周经验"]


class DataObj[T: DataName](ResponseData):
    name: T
    img: str | None = None
    key: str | None = None
    refreshTimeStamp: int | None = None
    expireTimeStamp: int | None = None
    value: object = None
    status: int
    cur: int
    total: int


class WuwaWidget(ResponseData):
    gameId: WuwaGameId
    userId: int
    serverTime: int
    serverId: str
    serverName: str
    signInUrl: str | None = None
    signInTxt: str
    hasSignIn: bool
    roleId: str
    roleName: str
    energyData: DataObj[Literal["结晶波片"]]
    livenessData: DataObj[Literal["活跃度"]]
    battlePassData: list[DataObj[Literal["电台等级", "本周经验"]]]


class WuwaWidgetGetDataRequest(WebRequest[WuwaWidget]):
    """鸣潮小组件数据"""

    gameId: WuwaGameId = GameId.WUWA
    roleId: str
    serverId: str
    type_: Literal[2] = Field(default=2, alias="type")
    sizeType: Literal[1] = 1

    @override
    def get_info(self) -> RequestInfo:
        return RequestInfo(
            url="https://api.kurobbs.com/gamer/widget/game3/getData",
            method="POST",
        )

    @override
    def get_response_data_class(self) -> type[WuwaWidget]:
        return WuwaWidget
