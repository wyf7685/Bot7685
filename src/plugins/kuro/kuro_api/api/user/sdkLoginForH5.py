# ruff: noqa: N815

from typing import final

from ..common import RequestInfo
from .sdkLogin import SdkLoginRequest


@final
class SdkLoginForH5Request(SdkLoginRequest):
    """验证码登录 Web 端"""

    _info_ = RequestInfo(
        url="https://api.kurobbs.com/user/sdkLoginForH5",
        method="POST",
    )
