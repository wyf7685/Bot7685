# ruff: noqa: N815

from typing import ClassVar, Literal, override

from ..common import (
    CommonRequestHeaders,
    RequestInfo,
    RequestWithoutToken,
    ResponseData,
)


class SdkLoginRequestHeaders(CommonRequestHeaders):
    token: str = ""

    @override
    def dump(self, *, without_distinct_id: bool = False) -> dict[str, str]:
        headers = super().dump(without_distinct_id=without_distinct_id)
        del headers["token"]
        return headers


class SdkLogin(ResponseData):
    enableChildMode: bool
    gender: int
    headUrl: str
    isAdmin: bool
    isRegister: int
    signature: str
    token: str
    """用户 token"""
    userId: str
    """账号 ID"""
    userName: str
    """昵称"""


class SdkLoginRequest(RequestWithoutToken[SdkLogin]):
    """验证码登录 APP 端"""

    _info_: ClassVar[RequestInfo] = RequestInfo(
        url="https://api.kurobbs.com/user/sdkLogin",
        method="POST",
    )
    _resp_: ClassVar[type] = SdkLogin

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
