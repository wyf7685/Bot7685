# ruff: noqa: N815

from typing import override

from ....common import Request, RequestInfo, ResponseData


class GetTotalGold(ResponseData):
    goldNum: int
    """库洛币总数"""


class GetTotalGoldRequest(Request[GetTotalGold]):
    """取库洛币总数"""

    @override
    def get_info(self) -> RequestInfo:
        return RequestInfo(
            url="https://api.kurobbs.com/encourage/gold/getTotalGold",
            method="POST",
        )

    @override
    def get_response_data_class(self) -> type[GetTotalGold]:
        return GetTotalGold
