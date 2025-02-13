# ruff: noqa: N815

from typing import override

from ...common import RequestInfo
from .sdkLogin import SdkLoginRequest


class SdkLoginForH5Request(SdkLoginRequest):
    """验证码登录 Web 端"""

    @override
    def get_info(self) -> RequestInfo:
        return RequestInfo(
            url="https://api.kurobbs.com/user/sdkLoginForH5",
            method="POST",
        )
