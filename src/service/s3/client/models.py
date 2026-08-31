import dataclasses
from datetime import datetime
from typing import Literal, TypedDict


class CompletedPart(TypedDict):
    PartNumber: int
    ETag: str


@dataclasses.dataclass(frozen=True, slots=True)
class HeadObjectOutput:
    content_length: int
    etag: str
    last_modified: datetime


@dataclasses.dataclass(frozen=True, slots=True)
class ListObjectsContents:
    key: str
    size: int
    etag: str
    last_modified: datetime
    is_dir: Literal[False] = False


@dataclasses.dataclass(frozen=True, slots=True)
class ListObjectsCommonPrefix:
    prefix: str
    is_dir: Literal[True] = True


__all__ = [
    "CompletedPart",
    "HeadObjectOutput",
    "ListObjectsCommonPrefix",
    "ListObjectsContents",
]
