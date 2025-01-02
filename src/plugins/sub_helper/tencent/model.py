from pydantic import BaseModel


class Response(BaseModel):
    RequestId: str


class DescribeRecordListResponse(Response):
    class _RecordCountInfo(BaseModel):
        SubdomainCount: int
        ListCount: int
        TotalCount: int

    class _RecordInfo(BaseModel):
        RecordId: int
        Value: str
        Status: str
        UpdatedOn: str
        Name: str
        Line: str
        LineId: str
        Type: str
        Weight: int | None
        MonitorStatus: str
        Remark: str
        TTL: int
        MX: int
        DefaultNS: bool

    RecordCountInfo: _RecordCountInfo
    RecordList: list[_RecordInfo]


class ModifyRecordResponse(Response):
    RecordId: int
