# ruff: noqa: N815

from typing import final

from .....const import GameId, WuwaGameId
from ....common import RequestInfo, ResponseData, WebRequest


class Item(ResponseData):
    type: int
    """
    物品类型

    奇藏 = 1
    信标 = 2
    声匣 = 3
    观景点 = 4
    飞猎手 = 5
    区域任务 = 6
    定风铎 = 8
    伏霜虫 = 9
    约兰的战术测试 = 11
    溢彩画 = 12
    藏宝地 = 13
    巡礼之梦 = 14
    三兄弟挑战 = 15
    全息战略·刀伶之舞 = 16
    音乐飞萤 = 17
    巡礼之梦·梦魇 = 18
    暗影徘徊的遗迹 = 19
    白月？绯月？ = 20
    三重冠塔 = 21
    声骸挑战·幻觉 = 22
    声匣·拉古那 = 23
    残息海岸 = 24
    青栎庭院 = 25
    """
    name: str
    """
    物品名称

    type 对应物品名称
    """
    progress: int
    """物品收集进度%"""


class AreaInfo(ResponseData):
    areaId: int
    """地区 id 2"""
    areaName: str
    """地区名称	云陵谷"""
    areaProgress: int
    """地区探索进度% 11"""
    itemList: list[Item]
    """地区的探索物品进度数组"""


class DetectionInfo(ResponseData):
    detectionId: int
    """
    残象 id

    310000090
    """
    detectionName: str
    """
    残象名称

    阿嗞嗞
    """
    detectionIcon: str
    """
    残象图标

    https://web-static.kurobbs.com/adminConfig/34/monster_icon/1716030815569.png
    """
    level: int
    """
    残象等级

    0-3 分别对应轻波, 巨浪, 怒涛, 海啸级
    """
    levelName: str
    """
    等级名称

    level 对应名称
    """
    acronym: str
    """残象名称音序

    azz
    """


class Country(ResponseData):
    countryId: int
    """国家代码 1"""
    countryName: str
    """国家名称 璜珑"""
    detailPageFontColor: str
    """详情页字体颜色 #bda757"""
    detailPagePic: str
    """详情页背景图 url"""
    detailPageProgressColor: str
    """详情页进度条颜色 #8c713a"""
    homePageIcon: str
    """首页图标 url"""


class Explore(ResponseData):
    areaInfoList: list[AreaInfo]
    """地区探索度数组"""
    country: Country
    """国家信息"""
    countryProgress: str
    """国家探索度% 86.45"""


class WuwaExploreIndex(ResponseData):
    exploreList: list[Explore]
    """地区探索度数组"""
    detectionInfoList: list[DetectionInfo]
    """残象探寻信息数组"""
    open: bool
    """对外显示"""


@final
class WuwaExploreIndexRequest(WebRequest[WuwaExploreIndex]):
    """鸣潮游戏角色探索数据"""

    _info_ = RequestInfo(
        url="https://api.kurobbs.com/aki/roleBox/akiBox/exploreIndex",
        method="POST",
    )
    _resp_ = WuwaExploreIndex

    roleId: str
    serverId: str
    gameId: WuwaGameId = GameId.WUWA
    channelId: int = 19
    countryCode: int = 1
