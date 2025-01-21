# ruff: noqa: N815

from typing import override

from pydantic import Field

from ....common import RequestInfo, ResponseData, WebRequest
from ....const import GameId


class BaseGoodsInfo(ResponseData):
    goodsId: int
    """物品 id"""
    goodsName: str
    """物品名称"""
    goodsNum: int
    """物品数量"""
    goodsUrl: str
    """物品图标链接"""
    isGain: bool
    """是否已获得"""
    serialNum: int


class DisposableGoodsInfo(BaseGoodsInfo): ...


class SignInGoodsInfo(BaseGoodsInfo):
    signId: int
    id: int


class SignLoopGoodsInfo(BaseGoodsInfo):
    signId: int


class InitSigninV2(ResponseData):
    disposableGoodsList: list[DisposableGoodsInfo]
    """新手(针对游戏角色)一次性签到签到奖励物品数组	已经做过了就是空数组"""
    # disposableSignNum: int = 5
    # """新手(针对游戏角色)一次性签到活动已签天数? 目前签满了就是 5 天"""
    eventEndTimes: str
    """本期活动结束时间"""
    eventStartTimes: str
    """本期活动开始时间"""
    expendGold: int
    """补签消耗库洛币数量"""
    expendNum: int
    """剩余补签次数	一个月 3 次"""
    isSignIn: bool = Field(alias="isSigIn")
    """今天是否已签到"""
    loopDescription: str | None =None
    """限时签到描述"""
    loopEndTimes: str | None = None
    """限时签到结束时间"""
    loopSignName: str | None = None
    """限时签到名称	限时签到 / 限时签到活动"""
    loopSignNum: int | None = None
    """限时签到已签天数"""
    loopStartTimes: str | None = None
    """限时签到开始时间"""
    nowServerTimes: str
    """当前服务器时间"""
    omissionNnm: int
    """漏签天数"""
    openNotifica: bool
    """弹窗通知(?)"""
    redirectContent: str
    redirectText: str
    redirectType: int
    repleNum: int
    signInNum: int = Field(alias="sigInNum")
    """签到天数"""
    signInGoodsConfigs: list[SignInGoodsInfo]
    """签到奖励物品数组"""
    signLoopGoodsList: list[SignLoopGoodsInfo]
    """限时签到奖励物品数组"""


class InitSigninV2Request(WebRequest[InitSigninV2]):
    """取游戏签到信息 V2"""

    gameId: GameId
    serverId: str
    roleId: str
    userId: str

    @override
    def get_info(self) -> RequestInfo:
        return RequestInfo(
            url="https://api.kurobbs.com/encourage/signIn/initSignInV2",
            method="POST",
        )

    @override
    def get_response_data_class(self) -> type[InitSigninV2]:
        return InitSigninV2
