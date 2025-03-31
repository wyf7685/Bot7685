# ruff: noqa: N815

from typing import Literal, final

from ...common import Request, RequestInfo, ResponseData


class LogItem(ResponseData):
    allowClick: bool
    createTime: int
    gold: int
    remark: str


class GoldLog(ResponseData):
    logList: list[LogItem]


@final
class GetGoldLogsRequest(Request[GoldLog]):
    _info_ = RequestInfo(
        url="https://api.kurobbs.com/encourage/gold/getGoldLogs",
        method="POST",
    )
    _resp_ = GoldLog

    pageIndex: int = 1
    pageSize: int = 10
    type: Literal[1, 2] = 1
    """
    1: 获取记录
    2: 消耗记录
    """
