# ruff: noqa: N815

from typing import override

from .....common import RequestInfo, ResponseData, WebRequest
from .....const import GameId, WuwaGameId


class ChallengeRole(ResponseData):
    natureId: int
    """属性 ID

    取值参考 `roleData` 接口的 `attributeId`
    """
    roleHeadIcon: str
    roleLevel: int
    roleName: str


class Challenge(ResponseData):
    bossHeadIcon: str
    bossIconUrl: str
    bossLevel: int
    bossName: str
    challengeId: int
    difficulty: int
    passTime: int
    roles: list[ChallengeRole] | None = None
    """未挑战时为 `None`"""


class WuwaChallengeDetails(ResponseData):
    challengeInfo: dict[str, list[Challenge]] | None = None
    """全息挑战数据

    键: ID (?) 对每个 boss 唯一
    值: boss 对应的挑战数据列表
        `未解锁`/`查询他人且未公开` 时为 `None`"""
    isUnlock: bool
    open: bool


class WuwaChallengeDetailsRequest(WebRequest[WuwaChallengeDetails]):
    """鸣潮全息战略数据详情"""

    gameId: WuwaGameId = GameId.WUWA
    roleId: str
    serverId: str
    channelId: int = 19
    countryCode: int = 1

    @override
    def get_info(self) -> RequestInfo:
        return RequestInfo(
            url="https://api.kurobbs.com/aki/roleBox/akiBox/challengeDetails",
            method="POST",
        )

    @override
    def get_response_data_class(self) -> type[WuwaChallengeDetails]:
        return WuwaChallengeDetails
