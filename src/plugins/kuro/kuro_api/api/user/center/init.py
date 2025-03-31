# ruff: noqa: N815

from typing import final

from ...common import Request, RequestInfo, ResponseData


class MoneyEnterInfo(ResponseData):
    channelId: int
    channelName: str
    state: int
    game2State: int
    game2MoneyUrl: str
    game3State: int
    game3MoneyUrl: str


class Game2CenterInfo(ResponseData):
    class _DownloadContent(ResponseData):
        urls: list[str]

    downLoadUrl: list[str]
    appStoreAppId: int | None = None
    downloadCloudContent: _DownloadContent
    downloadContent: _DownloadContent
    cloudState: int


class Game3CenterInfo(ResponseData):
    class _DownloadContent(ResponseData):
        urls: list[str]

    downLoadUrl: list[str]
    appStoreAppId: int | None = None
    appStoreCloudAppId: int | None = None
    downloadCloudContent: _DownloadContent
    downloadContent: _DownloadContent
    cloudState: int


class GameEnterInfo(ResponseData):
    channelId: int
    channelName: str
    game2CenterInfo: Game2CenterInfo
    game3CenterInfo: Game3CenterInfo


class HumanHelpInfo(ResponseData):
    game2HelpUrl: str
    game3HelpUrl: str


class UserCenterInitResponse(ResponseData):
    moneyEnterInfo: MoneyEnterInfo | None = None
    gameEnterInfo: GameEnterInfo | None = None
    humanHelpInfo: HumanHelpInfo | None = None
    moneyEnterState: int | None = None
    gameEnterState: int | None = None
    humanHelpEnterState: int | None = None


@final
class UserCenterInitRequest(Request[UserCenterInitResponse]):
    _info_ = RequestInfo(
        url="https://api.kurobbs.com/user/center/init",
        method="GET",
    )
    _resp_ = UserCenterInitResponse
