# ruff: noqa: N815

from typing import final

from ..common import Request, RequestInfo


@final
class SdkLogoutRequest(Request[bool]):
    _info_ = RequestInfo(
        url="https://api.kurobbs.com/user/sdkLogout",
        method="POST",
    )
    _resp_ = bool
