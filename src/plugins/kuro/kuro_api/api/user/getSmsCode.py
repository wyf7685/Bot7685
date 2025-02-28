# ruff: noqa: N815

from typing import final

from ..common import RequestInfo, RequestWithoutToken, ResponseData


class GetSmsCode(ResponseData):
    geeTest: bool
    """是否需要发送验证码"""


@final
class GetSmsCodeRequest(RequestWithoutToken[GetSmsCode]):
    """发送验证码 APP 端"""

    _info_ = RequestInfo(url="https://api.kurobbs.com/user/getSmsCode", method="POST")
    _resp_ = GetSmsCode

    mobile: str
    """手机号"""
    geeTestData: str | None = None
