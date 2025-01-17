# ruff: noqa: N815

from typing import override

from pydantic import Field

from .....common import RequestInfo, ResponseData, WebRequest
from .....const import GameId, WuwaGameId


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


class WuwaChallengeIndexRequest(WebRequest[WuwaChallengeIndex]):
    """鸣潮全息战略数据概览"""

    gameId: WuwaGameId = GameId.WUWA
    roleId: str
    serverId: str
    channelId: int = 19
    countryCode: int = 1

    @override
    def get_info(self) -> RequestInfo:
        return RequestInfo(
            url="https://api.kurobbs.com/aki/roleBox/akiBox/challengeIndex",
            method="POST",
        )

    @override
    def get_response_data_class(self) -> type[WuwaChallengeIndex]:
        return WuwaChallengeIndex
