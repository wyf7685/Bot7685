# ruff: noqa: N815

from typing import final

from ...common import Request, RequestInfo


@final
class IsRedPointRequest(Request[bool]):
    _info_ = RequestInfo(
        url="https://api.kurobbs.com/forum/dynamic/isRedPoint",
        method="POST",
    )
    _resp_ = bool
