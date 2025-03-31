# ruff: noqa: N815

from typing import final

from ...common import Request, RequestInfo


@final
class UserLoginLogRequest(Request[bool]):
    _info_ = RequestInfo(
        url="https://api.kurobbs.com/user/login/log",
        method="POST",
    )
    _resp_ = bool
