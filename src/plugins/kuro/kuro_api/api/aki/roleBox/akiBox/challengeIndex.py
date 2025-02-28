# ruff: noqa: N815

from typing import final

from pydantic import Field

from .....const import GameId, WuwaGameId
from ....common import RequestInfo, ResponseData, WebRequest


class Country(ResponseData):
    countryId: int
    countryName: str
    detailPageFontColor: str
    detailPagePic: str
    detailPageProgressColor: str
    homePageIcon: str


class IndexItem(ResponseData):
    bossHeadIcon: str
    bossIconUrl: str
    bossId: int
    bossLevel: int
    bossName: str
    countryId: int = Field(alias="contryId")
    difficulty: int


class Challenge(ResponseData):
    country: Country
    indexList: list[IndexItem]


class WuwaChallengeIndex(ResponseData):
    challengeList: list[Challenge]
    isUnlock: bool
    open: bool
    wikiUrl: str


@final
class WuwaChallengeIndexRequest(WebRequest[WuwaChallengeIndex]):
    """鸣潮全息战略数据概览"""

    _info_ = RequestInfo(
        url="https://api.kurobbs.com/aki/roleBox/akiBox/challengeIndex",
        method="POST",
    )
    _resp_ = WuwaChallengeIndex

    roleId: str
    serverId: str
    gameId: WuwaGameId = GameId.WUWA
    channelId: int = 19
    countryCode: int = 1
