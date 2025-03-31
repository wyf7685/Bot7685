# ruff: noqa: N815

from typing import final

from ..common import RequestInfo, RequestWithoutToken, ResponseData


class OpenScreenAd(ResponseData):
    contentType: int
    isNeedToken: int
    toAppAndroid: str
    toAppIOS: str
    startTimes: int
    endTimes: int
    name: str
    postId: str
    postTitle: str
    url: str
    showTime: int
    param: dict[str, object]


class GetOpenScreen(ResponseData):
    openScreenAd: list[OpenScreenAd]


@final
class GetOpenScreenRequest(RequestWithoutToken[GetOpenScreen]):
    _info_ = RequestInfo(
        url="https://api.kurobbs.com/config/getOpenScreen",
        method="POST",
    )
    _resp_ = GetOpenScreen
