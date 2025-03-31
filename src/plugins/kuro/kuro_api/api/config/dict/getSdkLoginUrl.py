# ruff: noqa: N815

from typing import final

from ...common import RequestInfo, RequestWithoutToken, ResponseData


class GetSdkLoginUrl(ResponseData):
    url: str


@final
class GetSdkLoginUrlRequest(RequestWithoutToken[GetSdkLoginUrl]):
    _info_ = RequestInfo(
        url="https://api.kurobbs.com/config/dict/getSdkLoginUrl",
        method="GET",
    )
    _resp_ = GetSdkLoginUrl
