from typing import TypedDict


class MultipartUploadPart(TypedDict):
    PartNumber: int
    ETag: str


class CompleteMultipartUploadPayload(TypedDict):
    Part: list[MultipartUploadPart]
