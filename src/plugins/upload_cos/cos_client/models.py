import dataclasses
from typing import TypedDict


class MultipartUploadPart(TypedDict):
    PartNumber: int
    ETag: str


class CompleteMultipartUploadPayload(TypedDict):
    Part: list[MultipartUploadPart]


@dataclasses.dataclass(frozen=True, slots=True)
class ObjectHeadResponse:
    content_length: int
    etag: str
