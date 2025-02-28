# ruff: noqa: N815

from typing import final

from .....const import GameId, WuwaGameId
from ....common import RequestInfo, ResponseData, WebRequest


class Phantom(ResponseData):
    name: str
    """声骸名称"""
    phantomId: int
    """声骸 id"""
    cost: int
    """声骸 COST"""
    iconUrl: str
    """声骸图标"""
    acronym: str
    """声骸名称音序"""


class PhantomListObj(ResponseData):
    phantom: Phantom
    """声骸信息对象"""
    star: int
    """已收集星级"""
    maxStar: int
    """最高星级"""


class WuwaCalabashData(ResponseData):
    level: int
    """数据坞等级"""
    baseCatch: str
    """基础吸收概率	20%"""
    strengthenCatch: str
    """强化吸收概率 80%"""
    catchQuality: int
    """最高可吸收品质"""
    cost: int
    """COST 上限"""
    maxCount: int
    """声骸收集进度上限"""
    unlockCount: int
    """当前声骸收集进度"""
    phantomList: list[PhantomListObj]
    """声骸信息数组"""


@final
class WuwaCalabashDataRequest(WebRequest[WuwaCalabashData]):
    """鸣潮游戏角色声骸收集数据"""

    _info_ = RequestInfo(
        url="https://api.kurobbs.com/aki/roleBox/akiBox/calabashData",
        method="POST",
    )
    _resp_ = WuwaCalabashData

    roleId: str
    serverId: str
    gameId: WuwaGameId = GameId.WUWA
