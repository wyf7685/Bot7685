# ruff: noqa: N815

from typing import Literal, override

from ...common import (
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
    gender: int
    signature: str
    headUrl: str
    headCode: str
    userName: str
    """昵称"""
    userId: str
    """账号 ID"""
    isRegister: str
    isOfficial: str
    status: str
    unRegistering: bool
    token: str
    """用户 token"""
    refreshToken: str


class SdkLoginRequest(RequestWithoutToken[SdkLogin]):
    """验证码登录 APP 端"""

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
            url="https://api.kurobbs.com/user/sdkLogin",
            method="POST",
        )

    @override
    def get_response_data_class(self) -> type[SdkLogin]:
        return SdkLogin