# ruff: noqa: N815

from typing import final

from ...common import Request, RequestInfo, ResponseData


class GetTotalGold(ResponseData):
    goldNum: int
    """库洛币总数"""


@final
class GetTotalGoldRequest(Request[GetTotalGold]):
    """取库洛币总数"""

    _info_ = RequestInfo(
        url="https://api.kurobbs.com/encourage/gold/getTotalGold",
        method="POST",
    )
    _resp_ = GetTotalGold
