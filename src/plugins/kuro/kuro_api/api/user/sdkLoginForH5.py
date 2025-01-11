# ruff: noqa: N815

from typing import Literal, override

from ...common import RequestInfo, RequestWithoutToken, ResponseData
from .sdkLogin import SdkLoginRequestHeaders


class SdkLoginForH5(ResponseData):
    enableChildMode: bool
    gender: int
    headUrl: str
    isAdmin: bool
    isRegister: int
    signature: str
    token: str
    userId: str
    userName: str


class SdkLoginForH5Request(RequestWithoutToken[SdkLoginForH5]):
    """验证码登录 Web 端"""

    mobile: str
    """手机号"""
    code: str
    """验证码"""
    devCode: str = ""
    gameList: Literal[""] = ""

    @override
    def create_headers(self, token: str) -> SdkLoginRequestHeaders:
        headers = SdkLoginRequestHeaders()
        self.devCode = headers.devCode
        return headers

    @override
    def get_info(self) -> RequestInfo:
        return RequestInfo(
            url="https://api.kurobbs.com/user/sdkLoginForH5",
            method="POST",
        )

    @override
    def get_response_data_class(self) -> type[SdkLoginForH5]:
        return SdkLoginForH5
