# ruff: noqa: N815

from typing import override

from ...common import RequestInfo, RequestWithoutToken, ResponseData


class GetSmsCode(ResponseData):
    geeTest: bool
    """是否需要发送验证码"""


class GetSmsCodeRequest(RequestWithoutToken[GetSmsCode]):
    """发送验证码 APP 端"""

    mobile: str
    """手机号"""
    geeTestData: str | None = None

    @override
    def get_info(self) -> RequestInfo:
        return RequestInfo(url="https://api.kurobbs.com/user/getSmsCode", method="POST")

    @override
    def get_response_data_class(self) -> type[GetSmsCode]:
        return GetSmsCode
